# Contributing

Use Python 3.12+ and Node 24. Follow README installation commands with the locked dependency files. Keep core inspection/policy independent of HTTP, use original fixtures, and preserve evidence offsets and trust metadata.

Before submitting changes run `pytest`, `ruff check .`, `ruff format --check .`, `mypy src`, `pip-audit -r requirements.lock`, and frontend `npm test`, `npm run build`, `npm audit`. Container changes also need `docker compose up --build -d --wait` and the functional smoke script. Optional real-model tests need lawful reviewed cached weights; do not describe mocks as real-model validation.

Add regression tests for important behavior and security fixes, especially denial precedence, parameter mutation, approval replay and untrusted identity assertions. Never weaken policy assertions to green a test. Document changed metrics and datasets honestly; do not optimize reported numbers by removing difficult cases or contaminating held-out sets.

No model weights, third-party datasets, API keys, full private prompts or generated audit databases should be committed. Contributions are MIT-licensed unless explicitly reviewed otherwise; retain any required third-party notices. Follow SECURITY.md for sensitive reports.
