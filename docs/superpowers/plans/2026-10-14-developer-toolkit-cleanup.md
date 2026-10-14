# Developer Toolkit Cleanup Implementation Plan

**Goal:** Make v0.2 a small, model-first Python toolkit with an installable public model, clear SDK/security boundaries, and an honest scanner dashboard.

**Base:** `docs/v0.2-architecture` at `89cc485`; this plan's branch targets that branch, leaving Draft PR #1 and `main` intact. The user's 14 October cleanup brief is the specification and explicitly authorizes implementation without a separate approval pause.

## Usage audit and disposition

| Area | Disposition | Evidence and reason |
|---|---|---|
| `guard.py`, preprocessing, `classifiers/local.py`, input policy | KEEP, SIMPLIFY | SDK, API and RAG consume one real-model path; bounded windows and fail-incomplete are core guarantees. |
| `classifiers/artifacts.py` | KEEP, EXTEND | Runtime verifies local safetensors; public download needs pinned revision and atomic verified install. |
| `guards/resources.py`, v2 action methods, executor, output guard | KEEP | Host-owned identity, grants, one-use approval, resource-version checks and release control are independent security boundaries. |
| `schemas.py` legacy action/output classes and `ActionGateway` v1 methods | REMOVE | Only `/v1` routes, legacy tests and example consume them; v2 contracts replace them. Keep shared `Decision`/`Source` types. |
| `/v1` routes and migration-only CLI `--mode` | REMOVE | Explicitly retired; no retained public user needs these. |
| API lab, evaluation, history and SQLite | REMOVE from everyday runtime | Dashboard uses these tabs, but none enforce authorization; retain local evaluation CLI/scripts and privacy-conscious audit logging. |
| API `/v2/scan`, capabilities, action/output, RAG and health | KEEP, SIMPLIFY | Scanner UI and external hosts use them; action/output endpoints return decisions but never execute tools. |
| Separate chatbot HTTP host | KEEP | Healthcare/enterprise boundary tests and examples use it; it is not mounted on the main scanner app. |
| Training/evaluation modules and original reports | MOVE TO DEVELOPMENT TOOLS / KEEP AS EVIDENCE | Reproduction and honest metrics need them, but ordinary CLI should focus on setup, doctor, scan and serve. |
| React scanner and evidence component | SIMPLIFY | Replace five-tab synthetic/metadata UI with one real-model score, threshold, window and source-span view. |
| Historical v0.1 archive and migration guide | REMOVE | They describe intentionally dropped interfaces; retain concise measured v0.2 evaluation and provenance. |

## Ordered tasks and checks

1. **Remove v1 contracts and runtime routes.** Add route-absence and v2 boundary tests first; delete old schemas/authority/approval paths, legacy examples/tests/config. Run Python security/API tests, Ruff and mypy. Commit.
2. **Public model onboarding and SDK.** Test pinned repository/revision/hash, staged download, per-file verification, no overwrite, offline inference, context-manager cleanup and missing-model diagnostics. Implement `kjnlae model download|verify`, platform data paths and concise errors. Run real public-weight download and doctor. Commit.
3. **Cross-platform and CLI.** Test worker resource-limit portability and path handling; retain only everyday CLI commands, move maintainer training/benchmark entry points to scripts. Add Windows/macOS no-model CI and mark real-weight platform checks unverified until executed. Commit.
4. **Scanner API and dashboard.** Remove runtime lab/evaluation/history/storage; expose actual threshold and all inspected window scores/spans, with no false clear status. Test API contracts, Unicode offsets, safe React rendering and responsive layout. Run real browser smoke. Commit.
5. **Docs and verification.** Rewrite README and create `CODEBASE.md`; update focused security/model/evaluation docs and examples, remove obsolete archives/links, record actual Linux and unverified platform results. Run full Python, frontend, audit, Docker and real-weight gates, independent review, then push feature branch and open PR against `docs/v0.2-architecture`.

**Security constraints throughout:** model-only prompt-injection classification; local verified safetensors; complete bounded inspection or explicit INCOMPLETE; independent host-owned authorization and output release; no raw prompt persistence; original reviewed weights and backups unchanged.
