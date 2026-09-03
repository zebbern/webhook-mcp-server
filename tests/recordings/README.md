# Recordings

Real exchanges with webhook.site, captured so offline tests assert on what the API actually returns instead of on shapes someone imagined.

| File | Produced by | Used by |
| ---- | ----------- | ------- |
| `live/http.jsonl` | `scripts/live_tool_check.py --record tests/recordings/live` (the server logs every HTTP exchange, tagged with the tool call that caused it) | `tests/test_replay_recordings.py` |
| `live/tools.json` | same run: every tool call with its arguments and result | `tests/test_replay_recordings.py` |
| `action_types_live.json` | `scripts/verify_action_types.py`: every Custom Action type run through `test-action` | `utils/action_types.json` (`verified` blocks) |

Re-record whenever a service or tool changes what it sends, or when the nightly live check fails: the replay test compares the current code's output against the recorded live result, so a mismatch means either a regression or an API change that must be looked at for real.

Personal data is replaced at record time (`utils/recorder.py`) with same-length stand-ins so truncated previews replay identically: real mailboxes become `userxxx@example.com`-style addresses, the active API key becomes `00000000-0000-4000-8000-0000000000ee`, public IPs `203.0.113.10`, user names `Recorded User`. Token and request UUIDs are kept; every token in here was deleted at the end of its run.
