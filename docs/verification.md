# Verification record

The exact results and local artifact provenance are in [model evaluation](reports/v0.2-model-evaluation.md), [feasibility probe](reports/v0.2-feasibility.md) and [fixture benchmark](reports/v0.2-fixture-benchmark.md). The test suite distinguishes offline core tests from optional actual-weight tests: a skipped real-weight test does not demonstrate model functionality. Use:

```bash
bash scripts/verify_all.sh
KJNLAE_VERIFY_RELEASE=1 KJNLAE_TEST_MODEL_DIR="$KJNLAE_MODEL_DIR" \
  KJNLAE_TEST_MODEL_HASH="$KJNLAE_MODEL_HASH" bash scripts/verify_all.sh
```

The script runs Ruff, mypy, Python tests, frontend tests/build and a wheel build; release mode additionally requires a local verified model, actual-weight integration tests, `doctor` and the measured benchmark. It exits nonzero if required checks fail. CI has no trained weights, so it runs core checks and records an explicitly incomplete model benchmark rather than claiming accuracy. The standalone Chromium smoke test is `KJNLAE_BROWSER_EXECUTABLE=/usr/bin/chromium python scripts/browser_smoke.py` against a loopback server with installed weights.

Record any failing command and its output rather than presenting a mocked test as real-weight evidence. A clean-wheel installation, actual Docker build, fresh Fedora installation and hosted CI outcome are separate integration checks; they should be reported as NOT_RUN if unavailable.
