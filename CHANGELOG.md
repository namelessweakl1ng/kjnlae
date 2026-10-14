# Changelog

## 0.3.0 — experimental developer-toolkit cleanup (2026-10-14)

- Added a pinned public-model download and verification workflow, per-user model paths, an SDK context manager, and full scored-window/threshold scan results. The model weights and their manifest identity are unchanged.
- Reduced the ordinary CLI to model install/verify, doctor, scan, and serve. Training, benchmarks, and synthetic demos moved to `python -m kjnlae.maintainer_cli`.
- Removed `/v1/*` endpoints and v0.1 action/approval schemas, the duplicate `/v2/guard/input` route, and the dashboard-only lab, evaluation, and history endpoints. SQLite history was removed; content remains out of application logs.
- Replaced the five-tab dashboard with a single accessible scanner showing actual scores, thresholds, windows, and mapped source evidence. No fabricated explanation or token attribution is shown.
- Preserved independent resource/tenant authorization, one-use human approval, guarded execution, RAG ACLs, and output release checks. Missing/corrupt/partial model inspection remains explicitly incomplete.
- Added Windows/macOS no-weight CI checks and platform setup instructions. Actual-weight Windows/macOS inference remains unverified.

This is a breaking change for v0.1 and for clients using removed convenience routes/CLI commands. Use `/v2/scan`, `kjnlae model download`, and the documented maintainer CLI. No automatic migration endpoint or classifier fallback is provided. The model remains experimental and has a 75% benign FPR on the 30-case regression fixture.
