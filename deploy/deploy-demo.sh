#!/usr/bin/env bash
# Publish the static demo to the live webroot. The demo runs over FICTIONAL personas, so
# generation is offline, deterministic, and needs no API keys (and web/demo/*.json is committed):
#
#   deploy/deploy-demo.sh             # publish the committed web/demo/*.json (no regeneration)
#   deploy/deploy-demo.sh generate    # regenerate the fictional runs offline, then publish
#
set -euo pipefail
cd /opt/sourcerer
WEBROOT=/var/www/drinkerlabs/sourcerer
SITE=https://drinkerlabs.info/sourcerer

if [[ "${1:-}" == "generate" ]]; then
  echo "generating cached demo runs (real GitHub + LLM)..."
  .venv/bin/python -m sourcerer.demo.generate
fi

# Refuse to publish an empty demo: the generator must have run at least once.
shopt -s nullglob
demo_json=(web/demo/*.json)
if (( ${#demo_json[@]} == 0 )); then
  echo "error: no web/demo/*.json to publish — run 'deploy/deploy-demo.sh generate' first" >&2
  exit 1
fi

echo "publishing static assets to ${WEBROOT}..."
mkdir -p "${WEBROOT}/demo"
cp web/index.html web/sourcerer.css web/sourcerer.js web/og.png web/favicon.png web/apple-touch-icon.png "${WEBROOT}/"
# --delete so a removed/renamed preset does not linger stale on the live site.
rsync -a --delete web/demo/ "${WEBROOT}/demo/"

echo "verifying live content (not just HTTP status — the site has an SPA fallback)..."
if ! curl -fsS "${SITE}/" | grep -q "<title>Sourcerer"; then
  echo "error: ${SITE}/ did not serve the expected page" >&2
  exit 1
fi
if ! curl -fsS "${SITE}/demo/manifest.json" | grep -q '"presets"'; then
  echo "error: ${SITE}/demo/manifest.json did not serve JSON (SPA fallback / stale?)" >&2
  exit 1
fi
echo "done — ${SITE}/ verified."
