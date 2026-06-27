#!/usr/bin/env bash
# Generate the cached demo runs, then publish the static demo to the live webroot.
# Requires OPENROUTER_API_KEY + GITHUB_TOKEN in /opt/sourcerer/.env (the generator
# makes real calls). Idempotent: overwrites web/demo/*.json and the webroot copy.
set -euo pipefail
cd /opt/sourcerer
WEBROOT=/var/www/drinkerlabs/sourcerer

echo "1/3 generating cached demo runs (real GitHub + LLM)..."
.venv/bin/python -m sourcerer.demo.generate

echo "2/3 publishing static assets to ${WEBROOT}..."
mkdir -p "${WEBROOT}/demo"
cp web/index.html web/sourcerer.css web/sourcerer.js "${WEBROOT}/"
cp web/demo/*.json "${WEBROOT}/demo/"

echo "3/3 done. Verify (the site uses an SPA fallback, so check CONTENT not just the 200 status):"
echo "  curl -s https://drinkerlabs.info/sourcerer/ | grep -q '<title>Sourcerer' && echo 'page OK'"
echo "  curl -s https://drinkerlabs.info/sourcerer/demo/manifest.json | head -c 40   # expect JSON {\"presets\":...}, not HTML"
