# Sourcerer demo (static)

The public demo at `drinkerlabs.info/sourcerer/`. Pure static — no backend, no
secrets on the public path. It **replays cached runs the pipeline generated over
fictional personas** (all links resolve to `example.com`), so the public demo
never publishes a real person's data. To research real, public GitHub candidates,
use the CLI.

## Files
- `index.html` / `sourcerer.css` / `sourcerer.js` — the page (committed).
- `demo/*.json` — cached runs + `manifest.json` (**committed**; safe to review, no PII).

## Regenerate the cached runs (offline, no keys)
Generation runs the real pipeline over deterministic mock clients seeded with the
fictional personas, so it needs no network and no API keys:

    /opt/sourcerer/.venv/bin/python -m sourcerer.demo.generate

The persona fixtures live in `sourcerer/demo/generate.py`.

## Publish to the live site
Publishes the committed `demo/*.json` (pass `generate` to regenerate first):

    bash /opt/sourcerer/deploy/deploy-demo.sh
