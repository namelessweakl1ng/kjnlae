# Deployment

Set `KJNLAE_MODEL_DIR` to the **verified local** fine-tuned artifact and `KJNLAE_MODEL_HASH` to the SHA256 of its `manifest.json`. Install CPU PyTorch 2.6.0, Transformers 4.51.3 and safetensors 0.8.0; see [Fedora installation](../README.md) and [artifact verification](model-training.md). The application never downloads weights at runtime. `kjnlae doctor` performs actual inference. `/health/live` means the process is running; `/health/ready` is 503 unless SQLite and the model worker are ready. A missing model still permits explicit incomplete scan responses and no sensitive execution.

Production requires `KJNLAE_ENV=production`, a random `KJNLAE_API_KEY` of at least 32 characters, pinned model directory/hash, allowed hosts and explicit CORS. Keep the server behind TLS, a real identity gateway and strict network controls. A static API key cannot represent different users or tenants. Supply per-user `HostAuthority` from verified credentials in embedded application code, or a restricted mode-0600 `KJNLAE_AUTHORITY_V2_FILE` for a single service identity. Never let prompt text or model output edit that file. Human approval issuance belongs to a trusted UI/backend ceremony and is intentionally absent from HTTP.

For local Compose, set in an uncommitted `.env`:

```text
KJNLAE_MODEL_DIR_HOST=./var/models/full-v0.2-v3-600/best
KJNLAE_MODEL_HASH=<sha256-of-manifest.json>
```

Then run `docker compose up --build -d` and check `curl http://127.0.0.1:8000/health/ready`. Compose mounts the model directory read-only, persists metadata in a volume, binds host port to `127.0.0.1`, runs as a non-root user with read-only root filesystem and drops Linux capabilities. The image includes CPU inference dependencies but no model weights. If no verified artifact is mounted, the container can be live but not ready; scans are incomplete. The cloud image build used its existing proxy CA as a BuildKit secret and a proxy hostname mapping; the resulting image passed readiness and HTTP smoke with real weights. Container UID 10001 must read the mounted directory and files. A host-only mode-700 artifact produces readiness 503; use a dedicated model copy or ACL granting that UID read access without changing the original artifact. Fresh Fedora/CI networking remains unverified.

The body limit is 128 KiB; text is capped at 32,768 characters; model windows, decoding, worker memory/time and rate are bounded. Default SQLite metadata retention is 500 records/7 days; set `KJNLAE_RETENTION=0` to disable insertion. Restrict database and authority-file permissions, encrypt host storage if policy requires it, and avoid storing full prompts or secrets in reverse-proxy logs. This code does not provide TLS termination, per-user sessions or distributed approval storage. Approvals are process-local, one-use and lost at restart; multiple workers require an external reviewed approval store before enabling sensitive actions.
