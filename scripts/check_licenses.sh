#!/usr/bin/env bash
# Receptra — license allowlist gate.
# Runs pip-licenses (backend) and license-checker (frontend) with the allowlists
# locked in research §5.4 + §5.5. Exits non-zero on any disallowed license.

set -euo pipefail

PY_ALLOW="Apache Software License;Apache 2.0;Apache-2.0;Apache-2.0 OR BSD-2-Clause;MIT License;MIT;BSD License;BSD-3-Clause;3-Clause BSD License;BSD-2-Clause;ISC License;ISC;ISC License (ISCL);Python Software Foundation License;PSF-2.0;The Unlicense;Mozilla Public License 2.0 (MPL 2.0);MPL-2.0 AND MIT;BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"

JS_ALLOW="Apache-2.0;MIT;ISC;BSD-2-Clause;BSD-3-Clause;CC0-1.0;0BSD;Unlicense;BlueOak-1.0.0"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

echo "==> Python license allowlist (backend)"
(
  cd backend
  uv run pip-licenses --allow-only="${PY_ALLOW}"
)
echo "✓ Python licenses OK"

echo ""
echo "==> JavaScript license allowlist (frontend)"
(
  cd frontend
  # Exclude the root package itself — license-checker reports any `"private": true`
  # package as UNLICENSED regardless of its `license` field. We DO have Apache-2.0
  # declared on receptra-frontend; this exclusion is ONLY for the private-workspace
  # self-reference, not for any third-party dep.
  npx license-checker --production --onlyAllow "${JS_ALLOW}" --excludePackages "receptra-frontend@0.1.0"
)
echo "✓ JavaScript licenses OK"
