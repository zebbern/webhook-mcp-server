# Releasing

Publishing is automated: a published GitHub release triggers `.github/workflows/publish.yml`, which runs the offline suite, builds the package, publishes to PyPI through the trusted publisher (OIDC, no token), then publishes `server.json` to the MCP registry.

## Before tagging

1. Bump the version in four places: `pyproject.toml`, `server.json` (`version` and `packages[0].version`), the install pins in `README.md`, and the heading in `CHANGELOG.md`.
2. Regenerate the docs: `python scripts/gen_tool_docs.py`.
3. Run the live tool check with recording and then the offline suite (see [testing.md](testing.md)). Both must be fully green; do not tag on a partial run.
4. Check the account is clean: `list_webhooks` shows only your own URLs.
5. Commit, push, and wait for the `Test` workflow (offline matrix plus the `live_auth` job).

## Tagging

```bash
git tag -a v3.0.0 -m "3.0.0"
git push origin v3.0.0
gh release create v3.0.0 --title "3.0.0" --notes-file <(sed -n '/^## \[3.0.0\]/,/^## \[/p' CHANGELOG.md | sed '$d')
```

Publishing the release starts the workflow. Watch it: `gh run watch`.

## After the release

- Confirm `uvx webhook-mcp-server==<version>` starts and `server_status` reports the key and socket.
- Run the model evals against the published package (`docs/testing.md`, section 5).
- Rotate the API key if it was used anywhere outside CI secrets and the local `.env.local`.

## One-time setup (already done)

- PyPI project `webhook-mcp-server` with a trusted publisher for `zebbern/webhook-mcp-server`, workflow `publish.yml`.
- Repository secret `WEBHOOK_SITE_API_KEY` for the live jobs.
