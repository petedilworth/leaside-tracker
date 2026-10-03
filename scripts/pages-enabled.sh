#!/usr/bin/env bash
# Tell the workflow whether GitHub Pages is switched on for this repository, so
# a deploy step can be skipped with a notice instead of failing the whole run.
# Writes enabled=true|false to GITHUB_OUTPUT.
set -euo pipefail
: "${GITHUB_TOKEN:?}"
: "${GITHUB_REPOSITORY:?}"
code=$(curl -s -o /tmp/pages.json -w '%{http_code}' \
       -H "Authorization: Bearer $GITHUB_TOKEN" \
       -H "Accept: application/vnd.github+json" \
       "https://api.github.com/repos/${GITHUB_REPOSITORY}/pages" || echo 000)
if [ "$code" = "200" ]; then
  url=$(python3 -c "import json; print(json.load(open('/tmp/pages.json')).get('html_url',''))")
  echo "enabled=true" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  echo "Pages is on: $url"
else
  echo "enabled=false" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  echo "::notice title=Page not published::GitHub Pages is not switched on (HTTP $code), so this run collected and saved but did not publish. Settings > Pages > Source: GitHub Actions. Steps in docs/PUBLISH.md."
fi
