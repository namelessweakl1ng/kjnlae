# Verification record

The exact results and local artifact provenance are in [model evaluation](reports/v0.2-model-evaluation.md), [feasibility probe](reports/v0.2-feasibility.md) and [fixture benchmark](reports/v0.2-fixture-benchmark.md). The test suite distinguishes offline core tests from optional actual-weight tests: a skipped real-weight test does not demonstrate model functionality. Use:

```bash
bash scripts/verify_all.sh
KJNLAE_VERIFY_RELEASE=1 KJNLAE_TEST_MODEL_DIR="$KJNLAE_MODEL_DIR" \
  KJNLAE_TEST_MODEL_HASH="$KJNLAE_MODEL_HASH" bash scripts/verify_all.sh
```

The script runs Ruff, mypy, Python tests, frontend tests/build and a wheel build; release mode additionally requires a local verified model, actual-weight integration tests, `doctor` and the measured benchmark. It exits nonzero if required checks fail. CI has no trained weights, so it runs core checks and records an explicitly incomplete model benchmark rather than claiming accuracy. The standalone Chromium smoke test is `KJNLAE_BROWSER_EXECUTABLE=/usr/bin/chromium python scripts/browser_smoke.py` against a loopback server with installed weights.

Record any failing command and its output rather than presenting a mocked test as real-weight evidence. On 2026-10-13 the follow-up candidate passed `KJNLAE_VERIFY_RELEASE=1 ... bash scripts/verify_all.sh`: 84 Python tests including real-weight API/chatbot tests, Ruff, strict mypy, 4 frontend tests, frontend build, wheel build, doctor and fixture benchmark. `pip-audit -r requirements.lock`, `pip-audit -r requirements-dev.lock` and `npm --prefix frontend audit --audit-level=low` found no known advisories at check time. The Dockerfile built locally after supplying the cloud proxy CA and mapping its proxy host; a Compose container with a UID-10001-readable private model copy returned readiness 200 and passed `python scripts/smoke.py`. A direct mode-700 host artifact returned readiness 503. With the same verified candidate, `/health/ready` returned 200 from the host server and `KJNLAE_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/browser_smoke.py` passed real scan, lab, evaluation, history, status, mobile layout and safe HTML rendering. This does not establish a fresh Fedora install or hosted CI success; inspect GitHub Actions after each push. See the [measured follow-up](reports/v0.2-followup-evaluation.md).
