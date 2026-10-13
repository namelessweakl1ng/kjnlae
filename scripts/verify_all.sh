#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${KJNLAE_VERIFY_RELEASE:-0}" == "1" ]]; then
  if [[ -z "${KJNLAE_TEST_MODEL_DIR:-}" || -z "${KJNLAE_TEST_MODEL_HASH:-}" ]]; then
    echo "Release verification requires KJNLAE_TEST_MODEL_DIR and KJNLAE_TEST_MODEL_HASH" >&2
    exit 2
  fi
  export KJNLAE_MODEL_DIR="$KJNLAE_TEST_MODEL_DIR"
  export KJNLAE_MODEL_HASH="$KJNLAE_TEST_MODEL_HASH"
fi

PY=.venv/bin/python
RUFF=.venv/bin/ruff
MYPY=.venv/bin/mypy
PYTEST=.venv/bin/pytest
if [[ ! -x "$PY" ]]; then
  PY=python
  RUFF=ruff
  MYPY=mypy
  PYTEST=pytest
fi

"$RUFF" check src tests examples scripts
"$RUFF" format --check src tests examples scripts
"$MYPY" src
"$PYTEST" -q
npm --prefix frontend test
npm --prefix frontend run build
"$PY" -m pip wheel --no-deps . -w /tmp/kjnlae-verify-wheel >/dev/null

if [[ "${KJNLAE_VERIFY_RELEASE:-0}" == "1" ]]; then
  "$PY" -m kjnlae.cli doctor >/tmp/kjnlae-doctor.json
  "$PY" -m kjnlae.cli benchmark --output /tmp/kjnlae-release-benchmark >/tmp/kjnlae-benchmark.log
  echo "Release checks: real model, fixture benchmark, tests and frontend passed"
else
  echo "Core checks passed. Actual-weight checks NOT_RUN without KJNLAE_VERIFY_RELEASE=1"
fi
