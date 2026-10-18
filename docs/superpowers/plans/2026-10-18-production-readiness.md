# kjnlae Production-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect independent evidence and harden kjnlae sufficiently for a controlled beta and a later, separate application-specific production review.

**Architecture:** Keep the verified local ONNX classifier as the sole prompt-injection detector. Build a separate, frozen evaluation pipeline; improve weights only when diagnostic evidence warrants it. Preserve independent host authorization, output release, explicit incomplete results and rollback throughout. Use five PRs with distinct review gates.

**Tech Stack:** Python 3.11–3.14, PyTorch/Transformers for optional CPU training, ONNX Runtime for normal inference, Pytest/Ruff/mypy, React/Vite, GitHub Actions, Hugging Face for a separately approved model release.

**Spec:** [production-readiness design](../specs/2026-10-18-production-readiness-design.md)

## Global Constraints

- Do not use opened 30/50/120 fixtures or Deepset TEST for new model selection; freeze a new family-disjoint final set before tuning.
- No paid compute, public weight upload, `main` merge, PyPI publication or default-installer switch without explicit owner release approval.
- v0.2 stays immutable and available for rollback. Every model identity has an immutable revision, safetensors/ONNX hashes and matching threshold.
- Model-only injection detection; no regex, untrained or mock fallback. A failed/incomplete scan is explicit; sensitive actions fail closed.
- No privileged action derives authority from scanner scores, prompts, retrieved text, agent output or untrusted HTTP fields.
- Every performance claim names its dataset, version, threshold, sample size, CPU hardware and uncertainty; beta is not production certification.

## Review Focus

1. A UTF-8 fixture containing U+2060 on Windows cp1252 must decode unchanged, and generated JSONL must retain LF bytes; PR 1 reruns these cases under a non-UTF-8 locale and hosted Windows.
2. A benign direct user request for another tenant's record must remain a classification negative while authorization denies access; PR 4 tests both results.
3. An attack after the first tokenizer window must be fully covered, or return `INCOMPLETE`; PR 4 tests the tail and mapped offsets with real ONNX weights.
4. Missing/corrupt weights during concurrent agent requests must never yield an authorized sensitive callback; PR 4 tests concurrent failure and rollback.
5. A fresh versioned model download into an occupied directory must refuse overwrite, and a tampered threshold must fail verification; PR 5 tests both before promotion.

---

### PR 1: Preserve artifacts and repair cross-platform CI

**Base/head:** `feat/v0.3-model-improvement` ← `fix/v0.3-phase0-readiness`.

**Files:** Modify `tests/training/test_v03_data.py`, UTF-8 text I/O in `src/kjnlae/`, `scripts/` and affected tests; update `README.md` and `docs/model-training-v0.3.md`; create this spec and plan. No weights or private transfer chunks enter the public repository.

**Interfaces:** `Path.read_text/write_text(..., encoding="utf-8")` for project-owned text. The public SDK/API and artifact identity stay unchanged.

- [x] Reproduce `test_v03_authored_text_never_copies_frozen_final_case` under `PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C`; observe `UnicodeDecodeError` before editing.
- [x] Add explicit UTF-8 and LF newlines to audited project Python text reads/writes, including the frozen fixture, dataset preparation, training/evaluation reports and model card staging. A Windows-newline simulation failed before and passed after the change.
- [x] Run the affected test and entire no-weight Pytest suite under the non-UTF-8 locale; verify no implicit `Path.read_text/write_text` calls remain in `src/kjnlae`, `scripts` or `tests`.
- [x] Verify original/ONNX manifests and archive checksums; encrypt the unchanged archive to the previously approved age public key; upload only numbered encrypted parts plus SHA256SUMS to the previously approved private repository; verify the remote commit and all part names/checksums.
- [x] Run local Ruff, mypy, frontend tests/build, wheel build, real candidate `doctor` and benchmark with `KJNLAE_VERIFY_RELEASE=1 bash scripts/verify_all.sh`; record skipped tests separately.
- [x] Push the PR 1 branch and verify hosted Linux, Windows, macOS, frontend and container jobs. [Quality run #151](https://github.com/namelessweakl1ng/kjnlae/actions/runs/39142368053) completed successfully at `927526b`; GitHub's PR API remains inaccessible from this workspace, so PR creation needs the manual compare link.
- [x] Review the PR 1 diff for unchanged artifact hashes, no secrets/plaintext weights, portability and test validity. The independent review found no actionable issues; no merge is requested.

### PR 2: Independent evaluation and frozen release evidence

**Files:** Create `src/kjnlae/evaluation/release_cases.py`, `scripts/evaluate_release.py`, `tests/evaluation/test_release_cases.py`, `tests/evaluation/test_external_adapters.py`, `datasets/fixtures/v0.4-frozen-final.jsonl`, `docs/reports/v0.4-experiment-protocol.md`; extend `src/kjnlae/evaluation/bipia.py` only where compatible. The v0.4 name identifies the next experiment, not an approved model release. Do not commit external dataset rows.

**Interfaces:** `load_cases(path: Path, expected_sha256: str) -> list[EvaluationCase]` and `check_partition_leakage(train: Sequence[EvaluationCase], final: Sequence[EvaluationCase]) -> None`; `scripts/evaluate_release.py` writes JSON with per-source/category confusion matrices, family counts, coverage and Wilson intervals. An AgentDojo adapter reports classifier scores and end-to-end outcomes separately.

- [ ] Write failing tests for incorrect fixture SHA, duplicate/family overlap, a Unicode tail-position case and an external label mapping mismatch; run them red.
- [ ] Implement validated case loading and leakage checks; create and commit the new frozen final set and its SHA/label guide **before** tuning or scoring it.
- [ ] Add separate development/diagnostic partitions; inspect licenses/attribution for BIPIA and AgentDojo. Implement only legally compatible imports and record excluded tasks.
- [ ] Write red metric tests for TP/TN/FP/FN, source/category breakdown, Wilson intervals and complete/incomplete counts; implement the report without discarding failures.
- [ ] Run historical diagnostics against current v0.3, BIPIA where compatible, and genuine AgentDojo tasks if its runtime/license can be reproduced; label any unrun integration honestly. Keep the new final set sealed.
- [ ] Run `python -m pytest tests/evaluation -q`, Ruff, mypy, fixture-hash/leakage checks; obtain a separate review of labels, split independence and benchmark claims.

### PR 3: Conditional model/data improvement

**Prerequisite:** PR 2 diagnosis shows a remediable data/model failure. If none is justified, document that result and omit this PR; do not train for a release number.

**Files:** Create `src/kjnlae/training/v04_data.py`, `scripts/prepare_v04.py`, `scripts/evaluate_v04.py`, tests under `tests/training/` and `tests/evaluation/`; modify `src/kjnlae/training/fit.py` or `src/kjnlae/evaluation/operating_point.py` only for a proven selection defect. Keep weights in ignored, private paths.

**Interfaces:** The prepared manifest records TRAIN/VALIDATION/CALIBRATION hashes and family/source counts. The selected threshold report binds model weight SHA, calibration hash, objective and selected epoch; packaging refuses a partial run or a failed gate.

- [ ] Write red leakage, label, source-balance and threshold-constraint tests for the diagnosed failure; run them before implementation.
- [ ] Add licensed public TRAIN-only and fictional original examples without copying any final case; compare recalibrated v0.3 before changing architecture.
- [ ] Run a bounded real CPU probe and record wall time, peak RSS and parameter change; fit only if the measured budget allows it.
- [ ] Freeze candidate weight hash, epoch and threshold on development data; then score the new final set **once** against v0.3 and the recalibrated control.
- [ ] If predeclared gates fail, preserve the report and v0.3 fallback; do not export or publish a new production model. If they pass, export separate safetensors/ONNX identities and test real-weight window/offset/decision parity.
- [ ] Run training/evaluation tests, full local real-model verification and independent review of false alarms, misses, licenses and reproducibility.

### PR 4: Dependency and end-to-end security hardening

**Files:** Add `tests/integration/test_offline_artifact_lifecycle.py`, `tests/security/test_agent_workflows.py`, and a controlled local agent harness under `examples/` or `src/kjnlae/evaluation/`; modify `src/kjnlae/guards/`, `src/kjnlae/classifiers/`, installer or API only for demonstrated defects. Update `docs/verification.md` and `docs/limitations.md` with executed evidence.

**Interfaces:** The harness returns both `scan_result` and `action_outcome` for fictional local resources; a model miss cannot grant a resource, tenant, tool or destination. The installer never overwrites an occupied path and scan never performs a network download.

- [ ] Write red tests for cross-tenant access, forged authority/approval, recipient substitution, output release, tail attack, missing/corrupt/timed-out weights, concurrent proposals and rollback.
- [ ] Fix only proven contract defects; retain trusted host identity and transactional resource/version checks. If a genuine local LLM agent run is feasible, use it with bounded synthetic tools and record model/version/seed; otherwise report that the agent-interaction gate is unverified, not simulated as passed.
- [ ] Build/install a wheel in clean Python environments; run offline real-weight CLI/SDK/API and Docker smoke on Linux. Run Windows/macOS real-weight checks where accessible and label other platform combinations unverified.
- [ ] Run `pip-audit` for default and optional training/build dependencies and `npm audit`; resolve high/critical runtime findings, document remaining optional advisories and supply-chain assumptions.
- [ ] Run `bash scripts/verify_all.sh` with real model pins, platform CI, and focused security review; publish actual authorized completion and unauthorized prevention counts.

### PR 5: Beta release package, versioning and documentation

**Files:** Update `docs/model-card-v0.3-candidate.md` if v0.3 is retained, or create `docs/model-card-v0.4-candidate.md` after a passing PR 3; update `docs/model-training.md`, `docs/model-data.md`, `docs/onnx-runtime.md`, `docs/verification.md`, `docs/limitations.md`, `README.md`, and `CHANGELOG.md` (create if absent); add issue templates/release notes where needed; test `scripts/publish_model.py` and installer identities. **Do not** update default model constants or `pyproject.toml` version during preparation.

**Interfaces:** A staged, separately versioned Hugging Face repository contains authentic safetensors/tokenizer/config/model card/manifest. Its immutable commit SHA and verified ONNX derivation hash are recorded before any promotion PR. Existing v0.2 directory and revision remain valid for rollback.

- [ ] Write red tests for mismatched revision/hash/threshold, occupied installation path, offline scanning after installation and rollback selection.
- [ ] Prepare a reviewable model card, release notes, migration/rollback guide, beta pilot protocol, support and incident route. State all false positives, missed attacks, unverified platforms and external benchmark gaps.
- [ ] Obtain license and independent security review. If criteria fail, retain experimental status and stop publication/promotion.
- [ ] Request **explicit owner approval** before any Hugging Face upload. After approval, publish to a new versioned repository, download its immutable revision afresh, verify every listed SHA and run offline real-weight acceptance on the downloaded copy.
- [ ] Request a **separate explicit owner approval** before a follow-up PR changes the default installer or Python package version. Do not merge, publish PyPI or claim production readiness from this plan alone.

## Handoff and reporting

Each PR report names its base/head, commit SHA, tests and hosted jobs actually observed, complete metrics, skipped/unverified checks, and next gate. PR 1 is the only implementation authorized in the present Phase 0 pass. Review this spec and plan before PR 2 work; future release promotion is a separate decision even if all test gates pass.
