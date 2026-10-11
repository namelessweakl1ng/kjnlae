# Evaluation methodology and provenance

Run `kjnlae benchmark --output reports/benchmark` to write a current JSON report and Markdown summary. The checked-in fixture dataset is `src/kjnlae/evaluation/fixtures.json`; it is included in wheels and referenced from `datasets/fixtures/README.md`. These 30 examples were authored for kjnlae and licensed under the repository MIT license. There are 18 attacks and 12 benign cases, including quoted attacks, code, ordinary HTML/Markdown, Unicode/encoding and an ambiguous security article.

This suite is a deterministic regression set, not training data or a held-out test set. Rules and fixtures were developed together, so contamination makes generalization claims invalid. No model was trained or fine-tuned. For real model comparisons, acquire separate lawful held-out data, freeze rules/model revision and thresholds first, retain provenance and avoid repeated tuning on the evaluation set.

## Detection metrics

Positive means a policy decision BLOCK or REQUIRE_REVIEW; WARN counts as negative. Compute TP/FP/FN/TN, precision TP/(TP+FP), recall TP/(TP+FN), F1, FPR FP/(FP+TN), FNR FN/(FN+TP). Empty class denominators report zero; category counts and confusion matrices disclose this ambiguity. Also report per-category results, mean/p95 latency, actual coverage, incomplete inputs and truncation behavior. Over-limit inputs are rejected or marked incomplete, not silently truncated.

Deterministic, ML-only and combined pipelines are evaluated separately. ML/combined are `not_run` when no classifier is configured. Unavailable classification yields `incomplete` and **no accuracy estimate**; fail-closed review responses must not be scored as successful ML detections. Model scores and policy thresholds have no calibration claim. Fixture runs do not measure arbitrary-length coverage; boundary tests separately exercise oversized/window/encoding budget behavior.

## Defense metrics

Six scenarios execute synthetic tool effects with and without independent authorization. Four adversarial cases target mock-secret reads, privileged tools, recipient diversion and a deliberate detector bypass. Two benign cases test educational analysis and an authorized read. Report attack success, authorized completion, benign rejection, unauthorized action prevention, control failure decision and measured defense overhead.

Success is an observable synthetic effect, not a detected phrase or an LLM refusal. The scripted proposal generator intentionally attempts the attacker action regardless of detection, so the policy boundary is exercised. The six cases do not establish a real LLM's attack success rate or summarization quality. One unavailable-control write probe demonstrates fail-closed behavior; unit tests separately cover read-only degradation, expiry, replay and mutation.

## BIPIA adapter

BIPIA's README, `bipia/data/base.py` and root license were inspected. The archived project has legacy dependencies and dataset-specific licenses: MIT code does not make all contexts MIT. WikiTableQuestions and Stack Exchange carry CC BY-SA requirements; WebQA/summarization have source acquisition restrictions. **No upstream data is committed here.**

In a separate environment, obtain a reviewed pinned BIPIA checkout and lawful context files. Use its documented builder:

```python
from bipia import AutoPIABuilder

builder = AutoPIABuilder.from_name("qa")(seed=2023)
rows = builder("your-lawful-test-contexts.jsonl", "your-test-attacks.json", enable_stealth=False)
rows.to_json("bipia-export.jsonl", orient="records", lines=True)
```

Then:

```bash
kjnlae import-bipia bipia-export.jsonl --output reports/bipia-cases.json
kjnlae benchmark --dataset reports/bipia-cases.json --output reports/bipia-detection
```

The importer checks bounded `context`, `attack_name` and `attack_str`, retains export SHA256/task metadata, and supports explicit boolean `attack` for locally added negative controls. Builder exports are typically attack-only, so include separately obtained legitimate contexts for meaningful false-positive measurements. This adapter measures detection, **not** BIPIA's LLM response attack-success metric. The adapter was tested with original schema fixtures; no external BIPIA data/evaluation was executed.

## AgentDojo integration path

The inspected upstream `BasePipelineElement.query(query, runtime, env, messages, extra_args)` API passes a message sequence and function runtime. In a separate pinned AgentDojo environment:

1. Add a pipeline element after tool-result collection and before model invocation. Scan only external/tool message content as `tool_response`; preserve the user query as trusted task context. Withhold/review according to result; never promote tool content to system authority.
2. Wrap `FunctionsRuntime` tool dispatch, mapping each supported runtime function into host-owned opaque resources, exact intent grants and constrained parameters. Use `ActionGateway` immediately before the underlying tool call. Do **not** derive grants from the proposed action or tool results. Reject functions without a mapping. Adapt schemas explicitly per suite.
3. Run the pinned benchmark command from upstream, with a lawful model/API configuration, then use its actual user-task/attack-success evaluator. Record suite/task IDs, attack, model/revision, defense version, denied calls and output evaluator. Compare the original and protected runtimes.

The upstream README example is `python -m agentdojo.scripts.benchmark -s workspace -ut user_task_0 -ut user_task_1 --model gpt-4o-2024-05-13 --defense tool_filter --attack tool_knowledge`. That is an upstream example, not a kjnlae-registered defense or an executed result. AgentDojo's API evolves and suite-specific permission mappings need integration work; no generic permission mapping is assumed. This documented path is deliberately separate from the default offline sandbox.
