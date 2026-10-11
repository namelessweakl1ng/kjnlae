# Verification record

Executed on 11 October 2026 with Python 3.12.14 and Node 24.19.0. Results below describe the implemented snapshot's local/cloud validation, not a security certification or a completed hosted GitHub Actions run.

| Check | Executed result |
|---|---|
| Installed package | Editable install and separate clean venv/wheel-style install succeeded; import reports 0.1.0; `pip check` clean |
| CLI | Structured injection scan, six-scenario demo through tests/API, measured benchmark and SDK approval example executed |
| Python suite | **47 passed, 1 skipped**; actual-weight model test skipped; one Starlette/httpx deprecation warning |
| Ruff | Lint and format checks passed |
| mypy | Strict check passed for 23 source files |
| Frontend | **3 tests passed**: escaped HTML, overlapping evidence, supplementary Unicode offsets |
| Frontend production build | TypeScript and Vite build passed |
| Real Chromium | Live scan/highlighting, six lab cases, measured evaluation, history/status, 390px mobile layout/credential field and non-executable submitted HTML passed |
| API runtime | Readiness, actual injection scan and independent action denial passed against both local server and container |
| Docker | Multi-stage image build succeeded; Compose start/health/functional smoke passed; UID 10001, audit DB mode 0600, loopback publish verified |
| Runtime Python audit | `pip-audit -r requirements.lock --vulnerability-service pypi`: no known vulnerabilities found |
| Frontend audit | `npm audit --audit-level=low`: zero advisories after patching Vitest to 5.0.3 |
| Fresh read-only code review | Separate reviewer found no blocking security defect; reviewer did not independently rerun tests |

The cloud Docker builder needed standard proxy arguments, a resolved proxy hostname and the environment's trusted CA bundle as an optional BuildKit secret mount. Plain builds initially failed DNS/TLS checks. Verification was preserved; no TLS/checksum/signature bypass was used. The final runtime image contains no proxy credentials or mounted build CA. Normal Compose configuration was syntax-validated, then the successfully built image was started with `docker compose up --no-build -d --wait` because the cloud-specific build plumbing is not a normal application requirement.

## Measured original fixtures

The actual JSON/Markdown reports are [benchmark-fixtures.json](benchmark-fixtures.json) and [benchmark-fixtures.md](benchmark-fixtures.md). Thirty original cases: 18 malicious, 12 benign. Confusion matrix: TP 17, FN 1, FP 1, TN 11. Precision/recall/F1: 0.9444; false-positive rate: 0.0833; false-negative rate: 0.0556. The difficult semantic bypass and ambiguous benign article are retained. Supported inspection coverage: 100% on this small suite, not a claim about all encodings or inputs.

Six synthetic boundary cases: four attacker actions were prevented, two legitimate read workflows completed. Guarded attack success 0/4; unguarded synthetic attacker goals observed in 4/4; authorized completion 2/2; benign rejection 0/2. Required-control failure blocked the tested write. These outcomes are derived from actual simulated state/output, not labels alone. Defense overhead and detector mean/p95 timings are measured in the report and vary by machine.

## Explicitly unverified

- Downloaded-model inference, model licenses/current cards/revisions and optional ML dependency audit: no reviewed weights were available. Adapter CPU execution and failure/timeout/busy handling exist; no real-model accuracy claim is made.
- External BIPIA/AgentDojo datasets, models and benchmark runs. BIPIA export adapter is tested only with original schema fixtures; AgentDojo integration remains a documented suite-specific path.
- Some primary research pages were blocked by the cloud proxy; see the research record in detection-engine.md.
- Hosted GitHub Actions results, newly restored cloud tasks, environment publication and real production deployment. Configuring CI or saving a cloud draft does not establish these outcomes.

## Reproduce optional browser checks

Install Playwright separately and obtain its browser using its official tooling, or use installed Chromium:

```bash
pip install playwright
KJNLAE_BROWSER_EXECUTABLE=/usr/bin/chromium python scripts/browser_smoke.py
```

Run the default development server or Compose first. Browser tooling is intentionally absent from runtime dependencies. The script performs only loopback requests and synthetic scenarios.
