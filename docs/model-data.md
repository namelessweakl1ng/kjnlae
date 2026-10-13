# v0.2 training data provenance

The committed `datasets/fixtures/v2_seed.jsonl` contains 100 original, fictional English examples: 64 TRAIN, 12 VALIDATION, 12 CALIBRATION, and 12 HELD_OUT_TEST. It contains 50 injection and 50 non-injection examples. The latter include educational quotations, source code, ordinary employee/patient access requests, and permitted reads. These labels describe **prompt-injection behavior in the stated source**, never the caller's authorization. The 30 v0.1 regression fixtures are excluded from training.

The optional public TRAIN source is Microsoft BIPIA's `benchmark/text_attack_train.json`, pinned to Git commit `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` and source SHA256 `63f95d3e67eac4178cdabdbdaf192cd05f2b6ed0702b578f1d30d556e5155670`. The importer selects 50 active instruction-shaping entries from ten categories and labels them as untrusted retrieved content. It excludes BIPIA's ordinary information requests and all external context corpora. We do not copy BIPIA into this repository. Its repository is MIT licensed for Microsoft-authored material, with separate dataset licenses and NOTICE for third-party components; the selected attack-prompt file is treated as Microsoft-authored. Users should retain BIPIA's LICENSE and NOTICE when importing it. BIPIA was archived in September 2026, so this pinned import is a frozen reference, not a maintained benchmark feed.

The Deepset dataset was considered but is not imported: its API advertises Apache-2.0 while nested dataset metadata says CC BY 4.0. A future importer would need to reconcile those terms and preserve attribution. AgentDojo is an external evaluation integration candidate; none of its data is in the present training partitions.

All original partition families are disjoint. The importer rejects cross-partition family, normalized text and near-duplicate leakage, and writes per-source and per-split SHA256 manifests. Public BIPIA examples are TRAIN-only; they cannot tune thresholds or report held-out scores. The tiny original held-out set measures software behavior on its specific examples and cannot establish broad real-world accuracy. Similarity to upstream encoder pretraining data is unknown. There are no real patient or company records.

To reproduce the current local combined training manifest after cloning the pinned BIPIA repository into `var/data/bipia`:

```bash
.venv/bin/python -c "from pathlib import Path; from kjnlae.training.dataset import import_bipia_attacks, prepare_dataset; p=Path('var/data/bipia/benchmark/text_attack_train.json'); out=Path('var/data/bipia-train.jsonl'); import_bipia_attacks(p,out,'a004b69ec0dd446e0afd461d98cb5e96e120a5d0'); print(prepare_dataset([Path('datasets/fixtures/v2_seed.jsonl'),out],Path('var/data/prepared'),42).counts)"
```

The measured local manifest has 114 TRAIN, 12 VALIDATION, 12 CALIBRATION and 12 HELD_OUT_TEST examples. Revalidate the pinned commit and source SHA256 before using it; a later clone or revised dataset is a different experiment.
