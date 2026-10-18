# Reproduce the English CPU model

For the separately evaluated, unpublished v0.3 continuation candidate, use
the [v0.3 training and Fedora guide](model-training-v0.3.md). The instructions
below reproduce the historical public v0.2 artifact; its weights and results
remain unchanged.

These instructions produce a new **local** artifact. The reviewed inference artifact is available through `kjnlae model download`; these instructions reproduce new weights locally. Use Python 3.12 or 3.13, four CPU cores, ample free disk and preferably 16–32 GiB RAM. The first cloud run used 660 TRAIN rows; the experimental follow-up used 924. Install CPU PyTorch and dependencies exactly as in the [README](../README.md). Do not train on held-out or regression cases or tune against them.

1. Acquire the pinned Apache-2.0 base model explicitly:

```bash
mkdir -p var/models var/data
python -m kjnlae.maintainer_cli prepare-base var/models/base-distilbert
```

This requests `distilbert/distilbert-base-uncased` revision `12040accade4e8a0f71eabdb258fecc2e7e948be`. The downloaded directory must contain `model.safetensors`, tokenizer and config files. No runtime scan downloads weights.

2. Acquire and verify the reviewed public sources. BIPIA is archived; the importer uses only its Microsoft-authored active attack-prompt file. Retain the BIPIA LICENSE and NOTICE. The Deepset dataset's API and nested metadata disagree between Apache-2.0 and CC BY 4.0; retain attribution and comply with both sets of obligations. Nothing is redistributed here.

```bash
git clone https://github.com/microsoft/BIPIA.git var/data/bipia
git -C var/data/bipia checkout a004b69ec0dd446e0afd461d98cb5e96e120a5d0
sha256sum var/data/bipia/benchmark/text_attack_train.json
curl -fL 'https://huggingface.co/datasets/deepset/prompt-injections/resolve/4f61ecb038e9c3fb77e21034b22511b523772cdd/data/train-00000-of-00001-9564e8b05b4757ab.parquet' -o var/data/deepset-train.parquet
curl -fL 'https://huggingface.co/datasets/deepset/prompt-injections/resolve/4f61ecb038e9c3fb77e21034b22511b523772cdd/data/test-00000-of-00001-701d16158af87368.parquet' -o var/data/deepset-test.parquet
sha256sum var/data/deepset-*.parquet
```

Expected SHA256: BIPIA `63f95d3e67eac4178cdabdbdaf192cd05f2b6ed0702b578f1d30d556e5155670`; Deepset train `2e10bc7ab30f542c97e4e83e2a5683000b5057d25ec10908784c631d44124c04`; Deepset test `39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e`. Stop if hashes differ.

3. Build the frozen split. The original 12-case exploratory test is omitted from this final experiment; the Deepset official test is the final held-out set. The committed 30-case regression suite is never training data.

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from kjnlae.training.dataset import import_bipia_attacks, import_deepset
seed = Path('datasets/fixtures/v2_seed.jsonl')
Path('var/data/original-v2.jsonl').write_text(''.join(
    line for line in seed.read_text().splitlines(keepends=True)
    if '"split": "HELD_OUT_TEST"' not in line and '"split":"HELD_OUT_TEST"' not in line
))
print(import_bipia_attacks(Path('var/data/bipia/benchmark/text_attack_train.json'),
    Path('var/data/bipia-train.jsonl'), 'a004b69ec0dd446e0afd461d98cb5e96e120a5d0'))
print(import_deepset(Path('var/data/deepset-train.parquet'),
    Path('var/data/deepset-train.jsonl'), 'TRAIN'))
print(import_deepset(Path('var/data/deepset-test.parquet'),
    Path('var/data/deepset-held_out_test.jsonl'), 'HELD_OUT_TEST'))
PY
python -m kjnlae.maintainer_cli train prepare --source var/data/original-v2.jsonl \
  --source var/data/bipia-train.jsonl --source var/data/deepset-train.jsonl \
  --source var/data/deepset-held_out_test.jsonl --output var/data/prepared-v2 --seed 42
```

Confirm `var/data/prepared-v2/manifest.json` reports `TRAIN=660`, `VALIDATION=12`, `CALIBRATION=12`, `HELD_OUT_TEST=116` and the split hashes in [data provenance](model-data.md). The importer rejects duplicate IDs, normalized/near-duplicate and family leakage across partitions. Public examples and trained weights stay ignored by Git.

4. Run the bounded feasibility probe before the full job. It runs at most 32 optimizer steps and 600 seconds, records load/step speed, memory and real parameter changes, exports safetensors and reloads them. Its output is **not** a detector artifact.

```bash
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train probe --base var/models/base-distilbert \
  --train var/data/prepared-v2/train.jsonl --output var/models/probe-v2
cat var/models/probe-v2/probe-report.json
```

If resources or session time are insufficient, stop. Do not silently reduce training or substitute a mock. The measured reference is [v0.2 feasibility](reports/v0.2-feasibility.md).

5. Fine-tune and evaluate only after a complete feasible probe. The fit process is bounded, uses batch 2, 128 tokens, AdamW at 2e-5, seed 42 and two epochs. It chooses the best checkpoint using VALIDATION only. Calibration chooses the threshold; the held-out test is evaluated afterward and compared with the seeded untrained-head control.

```bash
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train fit --base var/models/base-distilbert \
  --train var/data/prepared-v2/train.jsonl \
  --validation var/data/prepared-v2/validation.jsonl \
  --output var/models/full-v0.2-public --epochs 2
cat var/models/full-v0.2-public/fit-report.json
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train evaluate --fit var/models/full-v0.2-public \
  --prepared var/data/prepared-v2
```

If `fit-report.json` says `INCOMPLETE`, its output is not promoted. A slower CPU may hit the 300-second default deadline; use a documented and measured increase up to the code's 600-second cap, or train later on a separately approved environment. Check free disk before retraining because each run stores checkpoints and an initial control. No GPU is needed for this release.

6. Compute the new manifest hash and verify the newly produced model. The hash below belongs only to the executed cloud run; a new run can differ. Back up the entire `best` directory, not just the weights.

```bash
python -c 'from pathlib import Path; from kjnlae.classifiers.artifacts import verify_artifact; print(verify_artifact(Path("var/models/full-v0.2-public/best"), None))'
```

That checks the **training artifact**, not the application's ONNX runtime artifact. Application 0.3.2's `kjnlae model verify` and `doctor` accept only the separately reviewed ONNX derivative of the published checkpoint. A newly trained model requires its own graph hash, manifest and parity evaluation before promotion; do not point `Guard` at an unreviewed safetensors directory. A future GPU DeBERTa experiment requires a new reviewed training/evaluation and artifact contract; it is not a runtime fallback.

## Reproduce the experimental false-positive follow-up

Complete steps 1–3 above first. The 50-case independent fixture was frozen in commit `1a307c5` **before** these training changes and must never be included in TRAIN, VALIDATION or CALIBRATION. The 30-case regression fixture is also excluded. Regenerate only public TRAIN source variants and prepare the new split:

```bash
python -m kjnlae.training.augment --train var/data/prepared-v2/train.jsonl \
  --output var/data/deepset-benign-source-aug-v3.jsonl --count 200 --seed 43
python -m kjnlae.maintainer_cli train prepare --source var/data/original-v2.jsonl \
  --source var/data/deepset-train.jsonl --source var/data/bipia-train.jsonl \
  --source datasets/fixtures/v0.2-benign-train.jsonl \
  --source var/data/deepset-benign-source-aug-v3.jsonl \
  --source var/data/deepset-held_out_test.jsonl --output var/data/prepared-v3 --seed 42
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train fit --base var/models/base-distilbert \
  --train var/data/prepared-v3/train.jsonl \
  --validation var/data/prepared-v3/validation.jsonl \
  --output var/models/full-v0.2-v3-600 --epochs 2 --deadline 600
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train evaluate --fit var/models/full-v0.2-v3-600 \
  --prepared var/data/prepared-v3
```

Check for `status: COMPLETE` in `fit-report.json` before evaluation. The 924/12/12/116 manifest and all source hashes are recorded in [data provenance](model-data.md); the actual measurements and mixed results are in [follow-up evaluation](reports/v0.2-followup-evaluation.md). A 300-second attempt stopped incomplete before checkpointing, so 600 seconds is the tested bound on this four-core cloud machine, not a promise for every CPU.

To use **this** local candidate, install or copy the entire `best` directory and pin its manifest. A reproduction can have a different hash; compute and verify the hash of the artifact you actually produced.

```bash
export KJNLAE_TEST_MODEL_DIR="$PWD/var/models/full-v0.2-v3-reviewed"
python -c 'from pathlib import Path; from kjnlae.classifiers.artifacts import verify_artifact; print(verify_artifact(Path("var/models/full-v0.2-v3-reviewed"), "54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b"))'
kjnlae model download
kjnlae model verify
kjnlae doctor
```

The executed cloud candidate's manifest hash is `54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b`. Its local weights are ignored by Git. Preserve any new artifact and its `fit-report.json`, `evaluation-report.json`, prepared manifest and generated augmentation file separately. The published reviewed artifact has its own pinned manifest; do not overwrite it during reproduction.
