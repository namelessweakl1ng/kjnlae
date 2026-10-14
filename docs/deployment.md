# Deployment

Install the public artifact explicitly with `kjnlae model download`, then run `kjnlae model verify` and `kjnlae doctor`. The default model directory is per-user and inference is offline. For an advanced artifact, set `KJNLAE_MODEL_DIR` and `KJNLAE_MODEL_HASH` to a local directory and its manifest SHA-256. `/health/live` means the process responds; `/health/ready` is 503 until the verified model worker is available. Missing weights still yield explicit incomplete scan results. See the [platform quickstarts](../README.md).

Production requires `KJNLAE_ENV=production`, a random API key of at least 32 characters, explicit artifact path/hash, trusted hosts, and explicit CORS. Bind locally or behind a trusted TLS reverse proxy and identity layer. A static API key authenticates the deployment, not end users. For one service principal, a bounded, mode-0600 `KJNLAE_AUTHORITY_V2_FILE` can supply server-owned grants; a multi-user host should inject verified per-user authority. Never let prompt or model text modify that file. Human approval issuance belongs to a trusted host UI/backend and is not an HTTP route.

For local Compose, download to a dedicated project-local directory and set a private `.env`:

```bash
kjnlae model download --directory ./var/models/reviewed-v0.2
```

```text
KJNLAE_MODEL_DIR_HOST=./var/models/reviewed-v0.2
KJNLAE_MODEL_HASH=54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b
```

Then run `docker compose up --build -d` and check `curl http://127.0.0.1:8000/health/ready`. Compose mounts that artifact read-only, binds host port to loopback, runs as non-root UID 10001 with a read-only root filesystem, and drops capabilities. The image has CPU inference dependencies but no model weights. The installed model directory is private by default; grant UID 10001 read/traverse access to **that dedicated public-artifact copy** (for example with an ACL) before expecting container readiness. Do not change permissions on private training data or backups. No SQLite audit volume is needed; structured logs omit prompts.

HTTP bodies are capped at 128 KiB and text at 32,768 characters. Derived views, windows, inference time, and peer rate are bounded. Protect reverse-proxy logs from prompt bodies and secrets. This project does not provide TLS termination, per-user sessions, or durable distributed approval storage; approvals are process-local, one-use, and lost on restart. Multiple sensitive-action workers require a reviewed shared approval transaction before deployment.
