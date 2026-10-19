#!/usr/bin/env bash
# Lighthouse (mobile + desktop presets) against a production build of the landing page on the isolated stack.
# Scores are written to docs/lighthouse/landing-scores.json; full reports to /tmp/calibr-lh-*.html.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/lighthouse
E2E_FRONTEND=prod STACK_CMD='node ../scripts/lighthouse_run.mjs' frontend/e2e/run.sh
