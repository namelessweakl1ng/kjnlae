# Detection engine and research

## Inspection

Text is limited to 32,768 Unicode codepoints; request bodies to 128 KiB. Input is immutable. Per-codepoint NFKC normalization and format-control removal create a derived view with source mappings. This deliberately preserves evidence offsets; it is not full grapheme-level canonical normalization. Controls and hidden HTML are findings. HTML entities are inspected separately. Hidden CSS attributes and comments are evidence, not automatically proof of an attack.

At most 16 Base64 candidates (24..4,096 encoded characters) are decoded once as UTF-8 if largely printable. Longer candidates or more candidates mark inspection incomplete. Decoded text is never executed. Recursive Base64, hex, URL-encoded instructions and binary data are not comprehensive decoding features. HTML entity and normalized views are separate, so composed multi-stage obfuscation can evade rules. Completeness means the supported bounded views completed, not every possible encoding or language was understood.

Rules are individually bounded, stable and transparent. Findings contain category, explanation, severity, original `[start,end)` codepoint offsets, original evidence and derived-view name. Base64 findings point to the whole original encoded token. Role delimiters, overrides, hidden-prompt requests, sensitive-resource requests, exfiltration instructions, security bypasses, concealment and embedded execution directives are covered. Matches are evidence; they do not establish attack success.

## Context and decisions

`source`, `purpose`, `task`, `requested_action`, `sensitive_access` and `destination` are structured descriptive input. Source metadata is preserved; purpose explicitly marks legitimate analysis or code and downgrades suspicious evidence to `WARN`. Sensitive-access metadata increases suspicious severity. `task`, `requested_action` and destination are retained in the request for host use, not semantically interpreted as proof of alignment. The independent exact action policy enforces trusted intent and destination restrictions.

Default policy thresholds are WARN 25, REQUIRE_REVIEW 60 and BLOCK 80; scores are maximum ordinal evidence severity. Configure `ScanPolicy` from trusted host code; ordered thresholds are validated. ML positive score ≥0.8 contributes BLOCK severity. Thresholds have not been statistically calibrated. Missing classification or supported-inspection budget exhaustion requires review unless already blocked. Analysis claims can reduce screening severity and must never influence authorization.

## Optional actual ML

The executable adapter uses `AutoTokenizer` and `AutoModelForSequenceClassification`, PyTorch softmax and the explicit positive `id2label` index. It is not a rule-based imitation. Models require a 40-character commit revision, reviewed positive label, CPU tokenizer/model files, and safetensors weights. No `trust_remote_code` or pickle fallback. Default loading is local-cache-only and lazy. Use `pip install '.[ml]'` and explicitly obtain reviewed artifacts with Hugging Face tooling; access credentials belong in that tooling's secure configuration, not committed scripts.

The referenced model candidates have different constraints:

| Candidate | Integration judgment |
|---|---|
| Protect AI DeBERTa v2 | Sequence-classification adapter is a suitable format; larger CPU footprint; archived project means maintenance and provenance need extra review. Verify current license, label mapping and pinned artifacts before use. |
| Meta Llama Prompt Guard 2 22M | Smaller CPU candidate; access approval and Meta license restrictions apply. Verify gating, tokenizer dependencies, exact labels and safetensors availability. No license acceptance is automated. |

Neither model is redistributed or assumed universally accessible. No default model is selected without license/access review. Model-card access was blocked in this environment, so exact license terms, repository revisions and real-weight performance were **not verified**. Configuration makes the integration executable when lawful compatible artifacts are supplied.

The worker uses a separate spawned process, one PyTorch thread, 8 GiB address-space budget by default, 256-token windows, 32-token overlap, up to 128 windows and batch size 8. Over-limit token counts yield `coverage_exceeded`, never silently safe truncation. A single deadline covers loading and inference; expiry terminates the worker and discards uncertain state. Concurrent calls to a busy worker return explicit unavailable status rather than queueing without a bound. Linux is the supported memory-budget platform. Model identity, configured revision, windows and availability are reported. Scores are model outputs, not calibrated real-world attack probabilities. Mocked worker tests establish failure handling only; the opt-in `model` pytest smoke test requires actual cached weights.

## Research record (11 October 2026)

1. [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/): requested primary reference; web access blocked by proxy. No claim of direct page review.
2. [OWASP prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html): reviewed official [source](https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.md). Informs least privilege, exact approvals, origin separation, output controls and realistic bypass tests. No complete implementation copied.
3. [NIST AI 100-2e2025](https://csrc.nist.gov/pubs/ai/100/2/e2025/final): primary page blocked. Terminology uses attack surface, attacker control and observable outcomes; no assertion of NIST compliance or comprehensive taxonomy review.
4. [AgentDojo](https://github.com/ethz-spylab/agentdojo): reviewed README, pipeline interface and MIT license. Motivates separate attack-success and authorized-task metrics. Integration path documented, not executed.
5. [Microsoft BIPIA](https://github.com/microsoft/BIPIA): reviewed README, builder schema and root license including dataset exceptions. Archived September 2026 per assignment context; archival date was not independently confirmed. Import original builder exports without redistributing datasets or installing the legacy pipeline.
6. [Meta Prompt Guard 2](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M): model-card requests blocked; access/license requirements noted, no downloaded weights.
7. [Protect AI DeBERTa v2](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2): model-card requests blocked; archival status supplied by assignment, not independently confirmed here.

Remaining research access gaps are documented rather than replaced with fabricated review claims. The architecture follows independently verified prevention guidance and explicit authorization logic; no benchmark/model certification is claimed.
