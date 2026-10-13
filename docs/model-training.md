# Reproduce the English CPU model

These instructions produce a new **local** artifact. The model is not downloadable from this repository. Use Python 3.12+, four CPU cores, ample free disk and preferably 16–32 GiB RAM. The measured cloud run used 32 GiB and finished a bounded 32-step probe before a 660-step full run. Install CPU PyTorch and dependencies exactly as in the [README](../README.md). Do not train on the held-out test split or tune against it.

1. Acquire the pinned Apache-2.0 base model explicitly:

```bash
mkdir -p var/models var/data
kjnlae model prepare-base var/models/base-distilbert
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
kjnlae train prepare --source var/data/original-v2.jsonl \
  --source var/data/bipia-train.jsonl --source var/data/deepset-train.jsonl \
  --source var/data/deepset-held_out_test.jsonl --output var/data/prepared-v2 --seed 42
```

Confirm `var/data/prepared-v2/manifest.json` reports `TRAIN=660`, `VALIDATION=12`, `CALIBRATION=12`, `HELD_OUT_TEST=116` and the split hashes in [data provenance](model-data.md). The importer rejects duplicate IDs, normalized/near-duplicate and family leakage across partitions. Public examples and trained weights stay ignored by Git.

4. Run the bounded feasibility probe before the full job. It runs at most 32 optimizer steps and 600 seconds, records load/step speed, memory and real parameter changes, exports safetensors and reloads them. Its output is **not** a detector artifact.

```bash
HF_HUB_OFFLINE=1 kjnlae train probe --base var/models/base-distilbert \
  --train var/data/prepared-v2/train.jsonl --output var/models/probe-v2
cat var/models/probe-v2/probe-report.json
```

If resources or session time are insufficient, stop. Do not silently reduce training or substitute a mock. The measured reference is [v0.2 feasibility](reports/v0.2-feasibility.md).

5. Fine-tune and evaluate only after a complete feasible probe. The fit process is bounded, uses batch 2, 128 tokens, AdamW at 2e-5, seed 42 and two epochs. It chooses the best checkpoint using VALIDATION only. Calibration chooses the threshold; the held-out test is evaluated afterward and compared with the seeded untrained-head control.

```bash
HF_HUB_OFFLINE=1 kjnlae train fit --base var/models/base-distilbert \
  --train var/data/prepared-v2/train.jsonl \
  --validation var/data/prepared-v2/validation.jsonl \
  --output var/models/full-v0.2-public --epochs 2
cat var/models/full-v0.2-public/fit-report.json
HF_HUB_OFFLINE=1 kjnlae train evaluate --fit var/models/full-v0.2-public \
  --prepared var/data/prepared-v2
```

If `fit-report.json` says `INCOMPLETE`, its output is not promoted. A slower CPU may hit the 300-second default deadline; use a documented and measured increase up to the code's 600-second cap, or train later on a separately approved environment. Check free disk before retraining because each run stores checkpoints and an initial control. No GPU is needed for this release.

6. Compute the new manifest hash and verify the newly produced model. The hash below belongs only to the executed cloud run; a new run can differ. Back up the entire `best` directory, not just the weights.

```bash
export KJNLAE_MODEL_DIR="$PWD/var/models/full-v0.2-public/best"
export KJNLAE_MODEL_HASH="$(sha256sum "$KJNLAE_MODEL_DIR/manifest.json" | cut -d' ' -f1)"
kjnlae model verify "$KJNLAE_MODEL_DIR" --hash "$KJNLAE_MODEL_HASH"
kjnlae doctor
KJNLAE_VERIFY_RELEASE=1 KJNLAE_TEST_MODEL_DIR="$KJNLAE_MODEL_DIR" \
  KJNLAE_TEST_MODEL_HASH="$KJNLAE_MODEL_HASH" bash scripts/verify_all.sh
```

The local adapter validates hashes, labels, training steps and safetensors; disables remote code; runs on CPU in a timed worker; and reports incomplete if any supported view/window cannot be inspected. It does not accept arbitrary remote model IDs. A future GPU DeBERTa experiment requires a new reviewed training/evaluation and artifact contract; it is not a v0.2 runtime fallback.
