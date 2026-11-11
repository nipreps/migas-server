#!/usr/bin/env bash
set -euo pipefail

# Backward-compatibility check: installs a single migas-py ref and exercises
# its public API surface (see check_client_compat.py) against a running
# migas-server compose stack. Does not run migas-py's own bundled tests —
# those change layout release to release; the public API is what actually
# needs to stay compatible.
#
# Usage:
#   ./scripts/test_client_compat.sh <ref>
#
#   <ref> is any git ref installable via `pip install git+...@<ref>`:
#   a tag (e.g. 0.3.0), a branch (e.g. main), or a commit SHA.
#
# Env:
#   MIGAS_PY_GIT_URL    git URL to install migas-py from
#                       (default: https://github.com/nipreps/migas-py.git)
#   MIGAS_TOKEN         admin/master bearer token (default: dev_token, requires
#                       MIGAS_DEV=1 on the server — already set in docker-compose.yml)
#   MIGAS_TEST_PROJECT  project registered for the compat check (default: nipreps/migas-py)
#   KEEP_ARTIFACTS      set to 1 to skip venv cleanup for inspection
#   MIGAS_BUILDTYPE     Dockerfile BUILDTYPE for the server image (default: release,
#                       the locked build that ships; test-latest for unpinned deps)

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <ref>" >&2
  exit 2
fi
REF="$1"

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGAS_PY_GIT_URL="${MIGAS_PY_GIT_URL:-https://github.com/nipreps/migas-py.git}"
MIGAS_TOKEN="${MIGAS_TOKEN:-dev_token}"
MIGAS_TEST_PROJECT="${MIGAS_TEST_PROJECT:-nipreps/migas-py}"
KEEP_ARTIFACTS="${KEEP_ARTIFACTS:-0}"
MIGAS_BUILDTYPE="${MIGAS_BUILDTYPE:-release}"
VENV="$(mktemp -d "/tmp/migas-client-compat-${REF//\//_}.XXXXXX")/venv"

cleanup() {
  if [[ "$KEEP_ARTIFACTS" == 1 ]]; then
    echo "Keeping venv at $VENV"
    return
  fi
  rm -rf "$(dirname "$VENV")"
}
trap cleanup EXIT

echo "== Ensuring migas-server compose stack is up ($MIGAS_BUILDTYPE build) =="
(cd "$SERVER_DIR" && make compose-up BUILDTYPE="$MIGAS_BUILDTYPE")

SERVER_PORT="$(cd "$SERVER_DIR" && docker compose port migas-server 8080 | cut -d: -f2)"
SERVER_URL="http://localhost:${SERVER_PORT}"
# The server has no healthcheck, so `--wait` only guarantees the container started.
curl -sf -o /dev/null --retry 30 --retry-delay 2 --retry-all-errors "$SERVER_URL/"
echo "Server reachable at $SERVER_URL"

echo "== Registering test project '$MIGAS_TEST_PROJECT' =="
curl -sf -X POST "$SERVER_URL/api/admin/register" \
  -H "Authorization: Bearer $MIGAS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"project\": \"$MIGAS_TEST_PROJECT\"}"
echo

echo "== [$REF] installing migas-py =="
uv venv "$VENV" --python 3.11 >/dev/null
uv pip install -p "$VENV" "migas @ git+${MIGAS_PY_GIT_URL}@${REF}"

echo "== [$REF] running compat check =="
"$VENV/bin/python" "$SERVER_DIR/scripts/check_client_compat.py" \
  --server-url "$SERVER_URL" --project "$MIGAS_TEST_PROJECT"
