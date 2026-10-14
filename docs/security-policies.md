# Security policies and host authority

Input profiles (`general`, `rag`, `healthcare`, `enterprise`, `high_security`) apply the **verified model** score and threshold only after complete inspection. Missing, corrupt, timed-out or partial inference returns `INCOMPLETE` and review or block; sensitive profiles block. A high score can block lower-trust content, while a trusted analysis task may receive a warning. Neither score nor warning grants resource access. Deployment-owned policies are never accepted from request text.

Action authorization checks, in order: host-authenticated principal and tenant; allowed tool; current same-tenant resource; exact unexpired grant and version; destination and parameter restrictions; required-control readiness; and exact one-use human approval for side effects. Approval is bound to the action and parameters, principal, tenant, resource version and a short expiry. Only trusted host code may issue it after authenticating a distinct reviewer. `GuardedExecutor` executes only `ALLOW` and rechecks current resource state. Approval issuance and execution are absent from HTTP.

For a single service identity, `KJNLAE_AUTHORITY_V2_FILE` may point to a bounded trusted JSON file. Production requires mode 0600. A zero-privilege example:

```json
{"principal":"service","tenant":"local","task":"analysis","allowed_tools":[],"grants":[],"destinations":[],"resources":[]}
```

Multi-user applications should construct a fresh `HostAuthority` from authenticated application state and tenant-scoped records. An HTTP request cannot supply grants, reviewer status, or a catalog. One static API credential cannot identify different end users.

Output inspection checks known secrets and bounded decoded forms, external URL destinations, and structured keys. `OutputGuard.release` also checks trusted recipient, source resources and exact grants. It fails closed for resource release when required model controls are unavailable. Unknown secrets and nuanced disclosure cannot always be detected. Low-risk read-only authorization can return `WARN` in degraded mode, but the supplied executor does not execute `WARN`; a host needs a separately designed degraded path.
