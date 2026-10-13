# Migration from v0.1

v0.2 removes executable prompt-injection signatures, rule findings, ordinal rule severity, `deterministic` and `combined` modes, the third-party optional classifier adapter and silently successful scans without trained weights. Install our verified local fine-tuned model, set `KJNLAE_MODEL_DIR` and `KJNLAE_MODEL_HASH`, and run `kjnlae doctor` before accepting traffic. `kjnlae scan --mode ...` now exits with migration guidance.

Change `/v1/scan` or `/v1/guard/input` to `/v2/scan` or `/v2/guard/input`; v1 scan/input return 410. Remove `mode`, `purpose`, caller-asserted principal/approval fields from request bodies. Read `detection_status`, `policy_decision`, `model_status`, `model_score`, `evidence` windows and `inspection_complete`. `INCOMPLETE` means no successful classification, even if the application can still handle read-only analysis in a separately defined degraded path. Model scores are uncalibrated.

Use `/v2/guard/action` with server-owned `HostAuthority`, tenant/resource grants and `GuardedExecutor`; use `/v2/guard/output` for release. Existing v1 action/output endpoints remain guarded during transition but do not provide v2 tenant/version semantics. The lab and benchmark now execute only the trained model and independent action gateway. Historical rule results are archived under `docs/archive/` and are not current measurements.
