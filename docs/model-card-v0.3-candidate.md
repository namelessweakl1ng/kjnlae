---
language: en
library_name: transformers
pipeline_tag: text-classification
base_model: distilbert/distilbert-base-uncased
datasets:
  - deepset/prompt-injections
license: apache-2.0
inference: false
tags:
  - prompt-injection
  - experimental
  - release-candidate
---

# kjnlae DistilBERT v0.3 — local release candidate

**Experimental; not yet published.** This checkpoint is a candidate for
offline prompt-injection screening, not a guarantee that an agent will resist
attacks. It still falsely flags benign quotations, code, markup, and normal
workflows. Never use its output to grant access to a tool, secret, patient
record, employee record, or external recipient. kjnlae's independent host
authorization and output-release controls remain necessary.

The model is English-first. Labels are `NON_INJECTION` (0) and `INJECTION`
(1). A positive score indicates resemblance to learned prompt-injection
examples. The softmax value is **not** a calibrated probability of malicious
intent or attack success. A standard Transformers pipeline does not implement
kjnlae's source prefix, complete token-window coverage, threshold, or
authorization boundaries; use the verified ONNX gateway for application
scanning.

## Provenance and training

This candidate continues fine-tuning the verified
[`kjnlae-distilbert-v0.2`](https://huggingface.co/namelessweakling/kjnlae-distilbert-v0.2)
checkpoint at immutable revision `d6f5f455a4bc9b2c4587fc7f3011385a871e3653`.
That checkpoint derives from Apache-2.0 licensed
`distilbert/distilbert-base-uncased` revision
`12040accade4e8a0f71eabdb258fecc2e7e948be`. The v0.2 reviewed weight
SHA-256 is `0367a9d7b42f288a25d0d9f3c86d4b10b55b919652d504db535da28313b8f89a`.
The candidate's distinct safetensors SHA-256 is
`6c0896d72a1ef5bc5f49bd815412f8f66750055696ab716c6956ef872712c321`.

The 884-row TRAIN partition has 539 benign and 345 attack rows. It combines
Deepset TRAIN data, Microsoft-authored BIPIA TRAIN attack prompts, fictional
original v2 rows, 64 earlier hard benign rows, and 160 new fictional authored
rows. Newly authored, source-balanced VALIDATION (40 rows) and CALIBRATION
(80 rows) are family-disjoint from TRAIN. Source variants of the same text
remain within one family and one partition. Effective independent family
counts are smaller than row counts; especially, CALIBRATION has 40 authored
families. The new final test has 120 separately authored cases and was
committed before this experiment. No old 30-case, old 50-case, Deepset TEST,
or new final-test case was used for training, checkpoint selection, or
calibration. See the [data and probe report](reports/v0.3-data-and-probe.md)
for exact hashes and limitations.

Training used four CPU threads, seed 42, two epochs, batch size 2, 128 input
tokens, class-weighted cross-entropy, AdamW at 2e-5, gradient clipping, and
a bounded 600-second deadline. It completed 884 optimizer steps in 433.77
seconds wall time; peak worker RSS was 1,867,456,512 bytes. A separate
32-step real-weight probe preceded training. Validation F1 at 0.5 selected
epoch 2. A separately amended, explicit calibration objective selected
threshold **0.5**, requiring at most 10% benign false positives and at least
90% attack recall on CALIBRATION, then preferring higher recall and fewer
false positives. The initial poorly chosen tie-break and its correction are
preserved in the [protocol](reports/v0.3-experiment-protocol.md).

**Dataset rights:** Original synthetic examples are MIT licensed under this
repository. Preserve BIPIA's Microsoft-authored MIT license and NOTICE.
Deepset's top-level metadata reports Apache-2.0 while nested metadata
reports CC BY 4.0; retain attribution and observe both sets of obligations
until clarified. No public raw examples are redistributed with this card.
Some Deepset positive examples are ordinary roleplay or topic requests
without a host task context, making those labels ambiguous under kjnlae's
trust-boundary threat model. This is a known training-data limitation.

## Measured evaluation

Thresholds: published v0.2 `0.025134501978754997`; v0.2 recalibrated on
the new development CALIBRATION `0.9739183187484741`; v0.3 candidate `0.5`.
The final test was scored once after checkpoint/threshold selection.

| Set and model | TP | TN | FP | FN | Precision | Recall | F1 | Benign FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| New 120, published v0.2 | 40 | 46 | 34 | 0 | .541 | 1.000 | .702 | 42.5% |
| New 120, threshold-only v0.2 | 40 | 64 | 16 | 0 | .714 | 1.000 | .833 | 20.0% |
| **New 120, candidate** | **40** | **71** | **9** | **0** | **.816** | **1.000** | **.899** | **11.25%** |
| Old 50, published v0.2 | 15 | 25 | 10 | 0 | .600 | 1.000 | .750 | 28.6% |
| Old 50, candidate | 15 | 30 | 5 | 0 | .750 | 1.000 | .857 | 14.3% |
| Old 30, published v0.2 | 17 | 3 | 9 | 1 | .654 | .944 | .773 | 75.0% |
| Old 30, candidate | 16 | 6 | 6 | 2 | .727 | .889 | .800 | **50.0%** |
| Deepset TEST 116, published v0.2 | 58 | 47 | 9 | 2 | .866 | .967 | .913 | 16.1% |
| Deepset TEST 116, candidate | 57 | 56 | 0 | 3 | 1.000 | .950 | .974 | 0% |

On the new 120 cases, 95% descriptive Wilson intervals were 6.0–20.0% for
benign false-positive rate and 91.2–100% for recall. The samples are authored
and grouped by topic, so these intervals can understate real uncertainty.
The candidate missed no attack in this set but had nine benign false alarms:
one quotation, two code examples, two ordinary requests, one long analysis
document, and three markup/encoding examples. The old 30-case regression
remains particularly poor; it also has one more missed attack than v0.2.
These results do not establish population accuracy, multilingual quality, or
real-world attack success prevention. A separately pinned MIT-licensed
S-Labs TEST diagnostic of 2,101 mostly short direct-user prompts found
**4/1,050 benign false alarms but 359/1,051 labeled attacks missed** by this
candidate at its unchanged threshold. The public v0.2 control had 90 false
alarms and 182 misses on the same rows. Labels are unreviewed and some
positive examples appear ambiguous, so this is a distribution warning, not a
production estimate. See the [external diagnostic](reports/v0.4-external-diagnostic.md)
for source hashes, complete counts, CPU timings and the v0.2 control's partial
historical overlap check. Full AgentDojo and
external BIPIA benchmarks were not run.

The PyTorch checkpoint and a verified CPU ONNX derivative scored all 120
final cases in 124 mapped token windows. Maximum absolute per-window score
difference was `5.781650543212891e-06`, with zero decision flips and matching
window spans. The candidate ONNX model SHA-256 is
`aee933ab961a49d6c57ce0260220034b3e6e23177fc00602aa4e83578eb2106f`;
its manifest SHA-256 is
`537899c45553fc6583587684c5685d57c159c1b9f387590b182e1ce0f9a9ea4c`.
The source checkpoint manifest SHA-256 is
`071f6166177efd4af978e46d2f44fae13fe1a4be8c2030c916c3b924ecfe4d61`.
The weight-free ONNX graph template is unchanged because the architecture
and tensor shapes are unchanged; the filled graph and derivative manifest
have **new** hashes. Actual `Guard` scans completed all 120 inputs; warm mean
CPU latency was 24.31 ms versus 16.85 ms for v0.2 on this machine.

## Status and use

The verified local source and ONNX directories are in
`/workspace/kjnlae-v03-work/release-original` and
`/workspace/kjnlae-v03-work/release-onnx`. They are not in Git or on
Hugging Face. The existing public v0.2 model and default installer stay
unchanged. The proposed beta evidence gate is currently unmet; no Hugging
Face publication or default promotion is justified by these results. Advanced
local evaluators can opt in by pinning
`KJNLAE_MODEL_DIR` to the ONNX directory and `KJNLAE_MODEL_HASH` to the ONNX
manifest hash above. Never combine a v0.2 directory with a v0.3 hash.

The app's model-only detector returns `INCOMPLETE` on missing, corrupt,
timed-out, or incompletely scanned inputs. It never falls back to regex or an
untrained model. A clear scan does not authorize any action. This model card
must be updated with immutable publication revision and independent review
before public release.
