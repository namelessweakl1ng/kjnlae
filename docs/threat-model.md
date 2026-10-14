# Threat model

## Assets and attackers

Protect authorized tool effects, resource ownership, recipients, known sensitive output values and higher-priority application instructions. An attacker may control direct messages, retrieved documents, webpage HTML/text, email/attachment text, tool results, agent proposals and generated output. Treat model outputs and their parameters as untrusted, even after scanning.

Trusted components are host authentication, policy configuration, the reviewer ceremony, tool implementation, operating system, dependency installation and model-artifact supply chain. An attacker who controls these components can bypass the gateway. Authenticated API clients can submit analysis but cannot declare additional authority in request bodies.

## Boundaries

| Boundary | Enforcement |
|---|---|
| External content → model context | Preserve origin; inspection decision; never promote source into system authority |
| Proposed action → tool | Exact trusted intent, principal, tenant, resource grant/version, allowed tool/parameters, recipients |
| High-risk operation → execution | Exact principal/action-bound expiring one-use approval |
| Generated output → user/downstream | Known-secret matching, allowed hosts, expected structured fields, safe rendering |
| API client → policy | Server-owned deployment configuration; strict schemas reject forged authority |

The core question is whether untrusted content can induce deviation, unauthorized reads or unauthorized effects. The authorization gateway can prevent covered unauthorized actions regardless of detector recall. It cannot ensure a truthful summary, a model's reasoning, or faithful task completion outside its action constraints.

## In scope

Direct/indirect injection evidence, selected obfuscation, role spoofing, disclosure/exfiltration requests, action permission violations, approval substitution/replay/expiry, missing required control, privacy-preserving audit logging, request bounds, credentials and HTML-safe display. Sandbox secrets and destinations are synthetic `.test` fixtures.

## Out of scope

Compromised host/credentials, arbitrary tool adapters, arbitrary filesystem paths, network fetches, OCR/binary attachments, recursive decoding, fully multilingual detection, side-channel analysis, universal secret discovery, and LLM benchmark claims. Tool resource identifiers are opaque IDs resolved by host-owned code, not paths. No dynamic plugin loading, shell execution or live demonstration accounts exist.

## Failure boundaries

Oversized text is rejected. Encoded/window budget exhaustion is incomplete and requires review. An unavailable local trained model makes readiness fail and denies sensitive actions. Non-sensitive read authorization can return a degraded `WARN`, but the provided executor will not execute it. The runtime does not persist prompt history. Production fails at configuration time without credentials or a model pin.
