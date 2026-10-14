# kjnlae measured benchmark

**Historical, inactive v0.1 baseline.** The `deterministic` and `combined`
rows below record an earlier experiment. Current SDK, CLI, HTTP, dashboard and
integrations use only the verified fine-tuned model for injection detection;
this report is retained solely for reproducibility and comparison.

Dataset: kjnlae-original-regression-v1
SHA256: ecc953fd7e3ea64ef45301653c00600613d026640cd8c9b74cccae1029078932

Hand-authored regression cases; no held-out generalization estimate

| Detector | Precision | Recall | F1 | FPR | FNR |
|---|---:|---:|---:|---:|---:|
| deterministic | 0.9444 | 0.9444 | 0.9444 | 0.0833 | 0.0556 |
| ml | not_run | — | — | — | — |
| combined | not_run | — | — | — | — |

## Defense (six synthetic scenarios)

```json
{
  "attack_count": 4,
  "benign_count": 2,
  "attack_success_rate": 0.0,
  "unguarded_attack_success_rate": 1.0,
  "authorized_task_completion_rate": 1.0,
  "benign_task_rejection_rate": 0.0,
  "unauthorized_action_prevention_rate": 1.0,
  "control_failure_decision": "BLOCK",
  "control_failure_latency_ms": 0.06893300451338291,
  "mean_defense_overhead_ms": 0.09493249914764117,
  "simulation": "Scripted local tool proposals; no actual LLM benchmark"
}
```

These results do not establish resistance of any real LLM or external benchmark.
