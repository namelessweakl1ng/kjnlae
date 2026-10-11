# Deployment and development

## Local workflow

Use the existing checkout; cloud tasks are already isolated and need no additional worktree. Python 3.12+, Node 24 are the tested toolchains. Create a venv, install `requirements-dev.lock`, then `pip install --no-deps -e .`. Use the pinned frontend lock with `npm ci`. `kjnlae serve` binds loopback; `npm run dev` serves loopback and proxies the API. Build the frontend for same-origin serving from the backend.

`.env.example` is a reference, not automatically loaded by the Python CLI. Set variables in the process securely or use a trusted environment manager. Compose reads shell values / its `.env` interpolation; never commit real credentials.

## Container

`docker compose up --build -d --wait` builds a Node stage and Python 3.12 runtime with pinned dependency versions. It runs as UID 10001, mounts only an audit volume, publishes loopback, has a read-only root, a bounded temporary filesystem, drops all capabilities, and uses no-new-privileges, PID/CPU/memory limits. The image's internal bind is `0.0.0.0`; Compose's host bind remains `127.0.0.1`.

Run `python scripts/smoke.py` for readiness, a real injection scan and unauthorized action denial. `docker compose down` stops this project; add `--volumes` only when intentionally removing audit history. Optional model dependencies/weights are absent; ML needs a custom reviewed image/cache mount and a higher memory limit. Do not enable required ML on the default image and expect it to load.

Restricted cloud builders may need their provided HTTPS proxy propagated as Docker's standard build arguments and supported host networking. Use the environment's trusted certificate configuration if needed; never disable TLS or package verification. This is infrastructure plumbing, not an application requirement. Public deployments normally use Docker's standard network. Container validation results and any environment limits are recorded in `verification.md`.

## Production

Set `KJNLAE_ENV=production` and a securely generated high-entropy `KJNLAE_API_KEY` of at least 32 characters. Production refuses missing/short credentials and removes lab/evaluation/docs routes. Configure exact `KJNLAE_ALLOWED_HOSTS` and `KJNLAE_CORS_ORIGINS`; no wildcard production CORS. Terminate TLS at a mature reverse proxy or authenticated gateway; do not expose plain HTTP keys publicly. Run one application worker while approvals and rate limits remain process-local.

Mount a read-only deployment-owned authority file if needed and set `KJNLAE_AUTHORITY_FILE`. Never use an uploaded policy or grant all users the same broad service key. File integrity and authenticated task-to-grant mapping are part of the host's security boundary. The default is no resources and no tool permissions. SDK hosts can integrate richer per-user authorities without changing HTTP request trust.

`KJNLAE_OUTPUT_HOSTS` is an exact comma-separated host allowlist. `KJNLAE_OUTPUT_SECRETS_JSON` is a JSON array of known sensitive strings, injected securely; violations do not echo them. Do not include raw secrets in reports or examples. Known-resource output access remains a host responsibility.

Set `KJNLAE_REQUIRE_ML=1` only if reviewed compatible artifacts and optional dependencies are installed. Startup probes required classification; failed readiness returns 503 and required-control failure denies writes. ALLOW from a scanner does not override authorization. `KJNLAE_RETENTION=0` disables audit retention; default metadata ages out after seven days or 500 records.

## Dependencies and updates

`requirements.lock` pins tested runtime versions; `requirements-dev.lock` pins the test/tool environment. `frontend/package-lock.json` pins frontend resolution. Preserve TLS/signature/checksum verification. Re-run tests, type/build checks and vulnerability audits after upgrades. These locks pin versions but do not constitute a signed reproducible supply-chain attestation. Images should be pinned by reviewed digest by deployment operators; rolling upstream Python/Node base tags intentionally receive updates during local builds.

CI runs backend lint/format/type/tests/audit, frontend tests/build/audit, benchmark artifact generation and a Compose functional smoke. Actual hosted CI execution must be checked on GitHub; local equivalents do not prove a hosted run passed.

For a BuildKit builder behind a trusted TLS-inspecting proxy, the Dockerfile accepts an optional `build_ca` secret mount containing the supplied public CA bundle. Pass it with `docker build --secret id=build_ca,src=/path/to/trusted-ca.pem`. Standard proxy build arguments and `--add-host` may also be needed for that cloud's proxy hostname. The mounted CA is used only for verified pip/npm build requests and is not included in the resulting runtime image. Do not insert private keys or API credentials into a CA bundle. Normal builds need no custom CA.
