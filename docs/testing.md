# Testing

The rule behind every layer: a test is only valid if its expectation was checked against real webhook.site behaviour. Mocks whose shapes someone imagined do not count. That gives four layers, from cheapest to most real.

## 1. Offline suite (CI on every push)

```bash
pip install -e ".[dev]"
pytest -m "not live and not live_auth"
```

Unit tests plus the **replay tests**: `tests/test_replay_recordings.py` feeds the recorded HTTP exchanges from a real run through the current code and expects the recorded tool results. A mismatch means a regression or a platform change, never a guess.

`tests/test_docs_current.py` fails when `docs/TOOLS.md` or the README tool tables are stale (`python scripts/gen_tool_docs.py` regenerates both) or when the badge count is wrong.

## 2. Live tool check (needs an API key)

```bash
WEBHOOK_SITE_API_KEY=... python scripts/live_tool_check.py --record tests/recordings/live
```

Drives `server.py` over stdio like a real client, calls every tool (186 checks), verifies effects (the alias answers, the email arrived, the held request got the mocked response), deletes everything it created, and refreshes the recordings. Run it after any change to a service or tool, then run the offline suite so the replay matches. `.github/workflows/live-check.yml` runs it nightly.

Recordings (`tests/recordings/`):

| File | Produced by | Used by |
| --- | --- | --- |
| `live/http.jsonl` | the live tool check (every HTTP exchange, tagged with the tool call that caused it) | replay tests |
| `live/tools.json` | the same run (every tool call with arguments and result) | replay tests |
| `action_types_live.json` | `scripts/verify_action_types.py` | `utils/action_types.json` (`verified` blocks) |

Personal data is replaced at record time (`utils/recorder.py`) with same-length stand-ins so truncated previews replay identically: mailboxes become `userxxx@example.com`-style addresses, public IPs `203.0.113.10`, user names `Recorded User`, and the active API key `00000000-0000-4000-8000-0000000000ee`. Every token in a recording was deleted at the end of its run.

## 3. Live pytest tiers

```bash
pytest -m live         # anonymous URLs, no key
pytest -m live_auth    # needs WEBHOOK_SITE_API_KEY: real sign-up flow, socket wait, account listing
```

The `live_auth` job in `.github/workflows/test.yml` runs on pushes when the `WEBHOOK_SITE_API_KEY` secret exists.

## 4. Reference verification scripts

| Script | What it does |
| --- | --- |
| `scripts/gen_action_types.py <docs>/api/action-types.md` | regenerates `utils/action_types.json` from the docs; `LIVE_ADDITIONS` holds what the docs miss |
| `scripts/verify_action_types.py` | runs every action type through `test-action`; writes the `verified` blocks (never hand-edit them) |
| `scripts/gen_webhookscript.py <docs>/webhookscript` | regenerates `utils/webhookscript.json` |
| `scripts/verify_webhookscript.py` | calls every WebhookScript function name on the live engine |

## 5. Model evals (release testing only)

`evals/prompts/*.jsonl` holds 46 plain-language prompts with expectations (tools that must be called in order, alternatives, forbidden tools, argument regexes). `evals/run_evals.py` runs each in a headless `claude -p` session with only this server attached, real API calls included, and scores the trace.

```bash
WEBHOOK_SITE_API_KEY=... python evals/run_evals.py            # everything
python evals/run_evals.py --group actions                       # one group
python evals/run_evals.py --only create-03,action-02            # specific prompts
python evals/run_evals.py --model claude-sonnet-4-5             # another model
```

Results land in `evals/results/<timestamp>.md`. Each prompt is capped at 5 USD (`--budget`); the first turn alone costs about 0.7 USD on large models because the tool catalogue is cached, so a lower cap ends the session before any tool call. Webhooks the model created are deleted afterwards; schedules, groups, templates and variables named in the prompts may need deleting in the Control Panel.

A failing prompt usually means a tool description misled the model. Fix the wording, not the prompt. Evals cost real money and create real resources: run them for releases and after description changes, never as routine verification.

## Account safety for local runs

- Put the key in `.env.local` at the repo root as `WEBHOOK_SITE_API_KEY="..."`. The file is gitignored. Never print it, never read it from tests; export it into the environment for a run.
- Tokens created with a key are permanent: every probe deletes what it creates in a `finally`, then `list_webhooks` confirms.
- Guard any `send_email` action to a token's own inbox with a `condition` on `$request.type$`, or it loops.
- Never point an outbound action or schedule at a webhook.site URL; use `https://example.com/` as the harmless target. The platform disables recursive actions and emails the owner.
- Do not invite or delete real users, and do not send email to real addresses.
