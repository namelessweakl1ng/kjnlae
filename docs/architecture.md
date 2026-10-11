# Architecture

The core package depends on Pydantic, standard-library inspection and optional classification. It has no dependency on HTTP or the frontend. `Guard` combines evidence with `ScanPolicy`; `ActionGateway` and `OutputGuard` are independent interfaces. FastAPI is a transport adapter; `HistoryStore` defines the persistence contract and `SQLiteHistory` implements it. The CLI and HTTP adapter share the same core.

```mermaid
sequenceDiagram
    participant Source as Untrusted source
    participant Host as Trusted application
    participant Scan as Guard
    participant Agent as Agent/model
    participant Auth as ActionGateway
    participant Execute as Host executor
    Source->>Host: Data with origin/source type
    Host->>Scan: Inspect data; retain source metadata
    Scan-->>Host: Evidence + policy decision + completeness
    Host->>Agent: Accepted reference data (never system authority)
    Agent-->>Host: Proposed action (untrusted)
    Host->>Auth: Exact action + server-owned authority
    Auth-->>Host: Deny / require review / allow
    Host->>Execute: Execute only allowed immutable action
    Execute-->>Host: Result
    Host->>Host: OutputGuard before release
```

Prompts are never promoted into authorization policy. `source_trust` survives scanning and indicates user-supplied versus untrusted external data; it is descriptive, not a permission credential. The scanner preserves the original text, derived-view mappings and rule evidence. The host retains that provenance when constructing model context. The sandbox labels original sources and does not use their instructions to construct grants.

## Control boundaries

The host supplies exact intent grants, principal and ownership from an authenticated task. The API loads them from a deployment-controlled file once at startup; it starts with no grants. An API key authenticates a single service principal, not arbitrary end users. Multi-tenant applications must construct separate SDK authorities or isolate deployments and credentials. No request field can create a principal or approval.

Approvals are random opaque tokens held in process memory, bound to canonical action JSON, principal and expiry, and consumed under a lock. Host integrations must authenticate the reviewer and present the exact action. The API has no approval-creation endpoint. Restart invalidates approvals. A multi-worker/multi-node durable approval design is outside this version's scope; use a single worker.

The guard returns decisions; enforcement requires placing it next to the host's actual executor. kjnlae contains no real tool executor. In the sandbox, only allowed exact actions reach synthetic state-mutating tools. This demonstrates executable policy, not the behavior of a real LLM or live infrastructure.

## Operational design

A single spawned ML worker is lazy, CPU-only, bounded and terminated on timeout. Failed or exhausted classification explicitly marks inspection incomplete. The default rule path remains independent. SQLite retains only an allowlist of metadata with count/age limits. React renders all content as escaped text and maps Python codepoint spans correctly. The built frontend can be served by FastAPI; Vite's development proxy keeps normal development same-origin.

Tradeoffs: exact action grants are conservative and easy to audit, but need trusted application logic to enumerate intended operations. Static single-service API authentication is lean, but not a full identity provider. The original fixture suite catches regressions but is too small and coupled to development to estimate generalization. Optional model licensing and heavier dependencies remain the operator's responsibility.
