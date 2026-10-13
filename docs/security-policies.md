# Security policies and host authority

Input profiles (`general`, `rag`, `healthcare`, `enterprise`, `high_security`) apply only after a **complete** local-model result. Missing/corrupt/timed-out/partial inference returns `INCOMPLETE` and review or block, with sensitive profiles blocking. A score at/above the artifact threshold can block lower-trust content; trusted analysis may receive a warning. Thresholds and scores are not calibrated attack probabilities. Policy JSON under `configs/policies` is deployment-owned, not request-owned.

Independent action authorization checks, in order: authenticated host principal and tenant; allowed tool; same-tenant resource existence; unexpired exact grant and version; destination and parameter limits; required-control readiness; exact one-use human approval for sensitive actions. The approval digest binds the action and parameters plus principal, tenant and resource version, expires, and can be issued only by host code after a distinct authenticated reviewer. There is no HTTP approval issuance. `WARN` is never executed as `ALLOW` by `GuardedExecutor`.

For one server principal, set `KJNLAE_AUTHORITY_V2_FILE` to a bounded trusted JSON file. In production it must have mode 0600. Example with zero privileges:

```json
{"principal":"service","tenant":"local","task":"analysis","allowed_tools":[],"grants":[],"destinations":[],"resources":[]}
```

Real multi-user applications should construct a fresh `HostAuthority` from authenticated application credentials and tenant-scoped records rather than share a static API key identity. The HTTP request cannot supply grants, reviewer status or resource catalog. The v1 authority file is retained only for guarded transition endpoints.

Output release checks known secret strings and their bounded decoded forms, external URL host/userinfo restrictions, allowed structured keys, trusted recipients and current resource grants. It fails closed for resource release when required model controls are unavailable. This is deterministic **output protection**, not a prompt-injection detector. Unknown secrets and nuanced disclosure cannot be guaranteed detectable; hosts must minimize data access before generation.

Failure behavior is conservative: sensitive actions are denied if a required model control fails; read-only non-sensitive authorization can return `WARN` as a degraded decision but the provided executor does not execute it. Applications may build an explicit, separately authorized degraded read path; they must never turn `INCOMPLETE` into a successful scan.
