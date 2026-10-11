# Security policies

## Input screening

`ScanPolicy` sets ordinal thresholds; `Guard.scan` returns evidence and a decision without modifying or executing the input. BLOCK/REQUIRE_REVIEW mean the host must withhold or review input under its workflow. WARN carries evidence for benign analysis or low-severity structure. ALLOW does not prove safety. Untrusted scanning metadata has no effect on grants.

## Independent tool authorization

`Authority` belongs to trusted application code. It contains authenticated principal, owned resource IDs, exact `Grant(Action(...))` objects and exact allowed recipients. The API loads an `AuthorityFile` from a deployment-owned JSON path once at startup; without it, no action is granted. The static API key authenticates that configured service, not a body-specified end user. Never build grants by parsing model output or attacker-controlled documents.

Allowed action shapes are deliberately narrow:

| Tool | Parameters | Approval |
|---|---|---|
| `read_document` | Owned opaque resource ID; no recipient or extra parameters | None |
| `send_email` | Owned resource; exact allowed recipient; only bounded `body`/`subject` strings, exact intent match | Required |
| `delete_document` | Owned opaque resource; no recipient/extra parameters; exact intent | Required |
| `admin` | Unsupported | Always denied |

Policy precedence: authenticated principal → ownership → supported tool → exact trusted intent → parameter/destination validation → required-control availability → high-risk approval. Denial always wins; an approval never expands permission. Sensitive operations with unavailable required controls BLOCK. Authorized read-only operations in degraded mode WARN explicitly. No content can assert an unavailable control is healthy.

## Human approval ceremony

Only trusted host code invokes `ActionGateway.approve` after authenticating a reviewer and displaying the exact action. The token is cryptographically random, stored process-locally, bound to principal and SHA-256 of canonical action JSON, expires after 300 seconds by default and is consumed atomically. Modified parameters, recipient, resource, tool or principal invalidate it. Replay and expired tokens require review. Approvals cannot authorize `admin` or other permission violations.

There is intentionally no HTTP endpoint that turns a request's `approved=true` into approval. Hosts needing approval UIs must implement authenticated reviewer identity, CSRF/session controls and exact review binding outside model content. Keep one worker; restarts invalidate tokens. Execution adapters must hold the exact authorized action, resolve ownership securely, and avoid changes/races between authorization and effect.

## Output policy

`OutputGuard` matches configured exact known-secret strings in text and structured values, checks generated URL/HTML/Markdown destinations against exact host allowlists, and rejects unexpected structured fields. Relative absolute-path links can stay on the host; protocol-relative, credentialed, non-HTTP schemes and unapproved hosts are blocked. Structured keys are checked separately. Empty external-host allowlist denies external links. This is not arbitrary DLP: unknown/encoded secrets and misleading text can escape. Always apply destination-specific safe rendering and serialization.

## API security

Production requires a >=32-character configured API credential and constant-time comparison; a high-entropy random value is the operator's responsibility. All `/v1` routes are protected when a key is configured, including history and status. Liveness/readiness expose minimal operational state. CORS is explicit; trusted hosts prevent arbitrary host-header use. Lab/evaluation routes and public API docs are absent in production. Body limits, strict schemas and token-bucket limits apply. Rate limits use the actual peer, never unverified forwarded IPs. Use an upstream authenticated rate limiter for distributed deployments and multiple principals.
