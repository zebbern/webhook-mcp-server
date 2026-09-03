# Model-in-the-loop evals

The test suites prove the tools work when called correctly. This proves a model *calls them correctly* from plain requests, which is the only thing a user of this server experiences.

`prompts/*.jsonl` holds 46 prompts across diagnostics, webhooks, requests, email sign-up, custom actions, account features and security. Each carries expectations: tools that must be called in order, alternatives, forbidden tools, and argument regexes.

```bash
WEBHOOK_SITE_API_KEY=... python evals/run_evals.py            # everything
python evals/run_evals.py --group actions                       # one group
python evals/run_evals.py --only create-03,action-02            # specific prompts
python evals/run_evals.py --model claude-sonnet-4-5             # a different model
```

Each prompt runs in its own headless `claude -p` session with only this server attached (`evals/mcp.json`, the key comes from the environment), real API calls included. Results land in `evals/results/<timestamp>.md` with the tool trace per prompt; the raw streams are kept for anything that needs a closer look. Webhooks the model created are deleted afterwards.

Each prompt is capped at 5 USD (`--budget`); the first turn alone costs about 0.7 USD on the largest models because the 29-tool catalog is cached, so a lower cap ends the session before any tool call and shows up as "no tool calls" with `terminal_reason: budget_exhausted` in the stream file.

Run it before every release and whenever a tool description changes. A failing prompt usually means the description misled the model, not that the API broke; fix the wording, not the prompt.

Prompts that touch schedules, groups, templates and variables create real account resources under the names given in the prompts; delete them in the Control Panel if the model did not.
