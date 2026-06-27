# Sourcerer demo (static)

The public demo at `drinkerlabs.info/sourcerer/`. Pure static — no backend, no
secrets on the public path. It **replays** real pipeline runs that were
generated offline.

## Files
- `index.html` / `sourcerer.css` / `sourcerer.js` — the page (committed).
- `demo/*.json` — generated cached runs + `manifest.json` (git-ignored).

## Regenerate the cached runs (needs keys)
Requires `OPENROUTER_API_KEY` + `GITHUB_TOKEN` in `/opt/sourcerer/.env`
(the generator makes real GitHub + LLM calls):

    /opt/sourcerer/.venv/bin/python -m sourcerer.demo.generate

## Publish to the live site
    bash /opt/sourcerer/deploy/deploy-demo.sh
