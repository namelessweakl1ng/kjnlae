# Contributing

Use Python 3.11–3.14 and Node 24. Install the source checkout with `python -m pip install '.[api,dev]'`; add `[train]` only for maintainer training or original-PyTorch comparisons. `pyproject.toml` is the dependency source; the obsolete lockfiles were removed. Keep core inspection/policy independent of HTTP, use original fixtures, and preserve evidence offsets and trust metadata.

Before submitting changes run `bash scripts/verify_all.sh`, `python scripts/audit_cpu_dependencies.py`, `python -m pip_audit --progress-spinner off`, and `npm --prefix frontend audit --audit-level=low`. Container changes also need `docker compose up --build -d --wait` and the functional smoke script. The release gate needs verified local ONNX weights and `KJNLAE_VERIFY_RELEASE=1`, `KJNLAE_TEST_ONNX_DIR`, and `KJNLAE_TEST_ONNX_HASH`; do not describe mocks or no-weight CI as real-model validation.

Add regression tests for important behavior and security fixes, especially denial precedence, parameter mutation, approval replay and untrusted identity assertions. Never weaken policy assertions to green a test. Document changed metrics and datasets honestly; do not optimize reported numbers by removing difficult cases or contaminating held-out sets.

No model weights, third-party datasets, API keys, full private prompts or generated audit databases should be committed. Contributions are MIT-licensed unless explicitly reviewed otherwise; retain any required third-party notices. Follow SECURITY.md for sensitive reports.
