# Reproduce and review the v0.3 CPU model candidate

These instructions recreate a **local experiment**, not the exact reviewed
weight hash on every machine. The v0.3 candidate is not public yet. The
committed [protocol](reports/v0.3-experiment-protocol.md), [data/probe record](reports/v0.3-data-and-probe.md),
[evaluation](reports/v0.3-evaluation.md), and [model card](model-card-v0.3-candidate.md)
define the reference run. Do not tune another model against the now-opened
120-case final fixture; freeze a new independent test for future model
selection. Keep original public v0.2 weights and all new outputs separately.

## Fedora prerequisites and local environment

On a current Fedora release with Python 3.12 or 3.13 available:

```bash
sudo dnf install git curl python3 python3-devel gcc zstd nodejs npm
git clone https://github.com/namelessweakl1ng/kjnlae.git
cd kjnlae
git switch feat/v0.3-model-improvement
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install '.[train,api,dev]' pyarrow
python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
```

The reference cloud run used Python 3.12, PyTorch `2.6.0+cpu`, Transformers
`4.51.3`, ONNX `1.23.2`, four CPU threads, about 33 GiB total RAM, and a
32 GiB filesystem. Those versions and the exact [fit report](reports/v0.3-fit.json)
describe what was **actually used**, not a guarantee that the unpinned pip
command above will resolve identical versions later. For closest numerical
reproduction, install those versions in an isolated, offline-trusted training
environment; note the optional Transformers/setuptools advisories reported
in the [evaluation](reports/v0.3-evaluation.md). Default kjnlae runtime does
not need PyTorch or Transformers. Use `XDG_CACHE_HOME` and `HF_HOME` under a
writable directory if Fedora/cloud home caches are read-only.

## Acquire the exact allowed sources

The reference v0.3 experiment **continued from v0.2 weights**, not from a
fresh random head. Explicitly download and verify the unchanged published
v0.2 safetensors. This network operation is separate from normal offline
inference:

```bash
mkdir -p var/models var/data
python - <<'PY'
from pathlib import Path
from kjnlae.classifiers.artifacts import download_public_model, verify_artifact
target = Path('var/models/v02-source')
print(download_public_model(target))
print(verify_artifact(target, '54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b'))
PY
```

Fetch only pinned public TRAIN sources. Preserve BIPIA LICENSE/NOTICE and
Deepset attribution and both reported license obligations. The test parquet
is **not** a training source:

```bash
curl -fL --retry 3 \
  'https://huggingface.co/datasets/deepset/prompt-injections/resolve/4f61ecb038e9c3fb77e21034b22511b523772cdd/data/train-00000-of-00001-9564e8b05b4757ab.parquet' \
  -o var/data/deepset-train.parquet
curl -fL --retry 3 \
  'https://raw.githubusercontent.com/microsoft/BIPIA/a004b69ec0dd446e0afd461d98cb5e96e120a5d0/benchmark/text_attack_train.json' \
  -o var/data/bipia-text-attack-train.json
sha256sum var/data/deepset-train.parquet var/data/bipia-text-attack-train.json
```

Expected source SHA-256 values are
`2e10bc7ab30f542c97e4e83e2a5683000b5057d25ec10908784c631d44124c04`
and `63f95d3e67eac4178cdabdbdaf192cd05f2b6ed0702b578f1d30d556e5155670`
respectively. `scripts/prepare_v03.py` verifies both before using them,
checks family and near-duplicate partition leakage, excludes the old v2
validation/calibration cases, and checks the frozen test for lexical overlap:

```bash
python scripts/prepare_v03.py \
  --deepset-train var/data/deepset-train.parquet \
  --bipia-train var/data/bipia-text-attack-train.json \
  --output var/data/v03
cat var/data/v03/data-summary.json
```

Reference counts are TRAIN 884, VALIDATION 40, CALIBRATION 80, with split
hashes in [data/probe](reports/v0.3-data-and-probe.md). Raw public training
rows, prepared splits, and model weights belong in ignored/private local
storage, not Git. The 120-case frozen fixture has already informed this
candidate's release decision; **do not use it to select a new model**.

## Bounded probe and full fine-tuning

Run the 32-step real optimization probe first. The reference probe took
28.92 seconds wall time, used 1.75 GiB peak worker RSS, and changed encoder
parameters. If it fails or predicts that the full run will exceed local
limits, stop rather than accepting a partial checkpoint.

```bash
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train probe \
  --base var/models/v02-source \
  --train var/data/v03/prepared/train.jsonl \
  --output var/models/v03-probe
cat var/models/v03-probe/probe-report.json
```

The measured full run used two epochs, 884 total batch-two optimizer steps,
128-token training inputs, class-weighted cross-entropy, AdamW at 2e-5,
seed 42, and a 600-second upper bound. Its selected epoch was 2. The current
training code truncates individual TRAIN examples at 128 tokens, while
inference covers long inputs with multiple windows; do not assume a long
attack near the end is directly learned from a long training example.

```bash
HF_HUB_OFFLINE=1 python -m kjnlae.maintainer_cli train fit \
  --base var/models/v02-source \
  --train var/data/v03/prepared/train.jsonl \
  --validation var/data/v03/prepared/validation.jsonl \
  --output var/models/v03-fit \
  --epochs 2 --deadline 600
python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('var/models/v03-fit/fit-report.json').read_text())
assert p['status'] == 'COMPLETE' and p['steps'] > 0, p
print(p['best_epoch'], p['best_weight_sha256'], p['parent_wall_seconds'])
PY
```

An `INCOMPLETE` report is not a model artifact. If training finishes but
differs from the reference hash, it is a **new** candidate requiring its own
reviewed threshold, final test, ONNX graph hash, and application pin.

## Select, evaluate, and package a new local candidate

The reference experiment used a larger calibration partition and sealed
threshold before evaluating the final fixture. The `development` command
checks for an already existing selection file; use a fresh output directory:

```bash
HF_HUB_OFFLINE=1 python scripts/evaluate_v03.py development \
  --control var/models/v02-source --fit var/models/v03-fit \
  --prepared var/data/v03/prepared --output var/eval/v03
cat var/eval/v03/selection.json
```

Run the `final` phase **only for a checkpoint and threshold selected without
consulting its final data**. The committed 120-case fixture was used for the
reference run and is no longer independent of future development decisions.
For a new release experiment, create and freeze a different final set and
update the script's pinned hash and acceptance protocol before training.

```bash
HF_HUB_OFFLINE=1 python scripts/evaluate_v03.py final \
  --control var/models/v02-source --fit var/models/v03-fit \
  --prepared var/data/v03/prepared --output var/eval/v03
python scripts/package_v03_candidate.py \
  --control var/models/v02-source --fit var/models/v03-fit \
  --selection var/eval/v03/selection.json \
  --final var/eval/v03/final-comparison.json \
  --original-output var/models/v03-candidate-source \
  --onnx-output var/models/v03-candidate-onnx
```

The packager refuses incomplete training, changed weights/selection, or a
failed frozen-set gate. It copies safetensors and tokenizer files, writes a
per-file integrity manifest, fills a verified weight-free DistilBERT ONNX
template, checks its tensor names/shapes and graph, and records distinct
source/ONNX hashes. The application accepts **only reviewed, code-pinned**
ONNX hashes; a newly reproduced weight hash will not automatically be
accepted. This is deliberate fail-closed behavior, not a prompt-injection
detector fallback. Review and pin a new artifact identity before deployment.

For the actual reference candidate, the verified source and ONNX directories
are `/workspace/kjnlae-v03-work/release-original` and
`/workspace/kjnlae-v03-work/release-onnx`. They are not included in Git.
After securely transferring both whole directories to Fedora, verify them:

```bash
sha256sum /PATH/TO/release-original/manifest.json \
  /PATH/TO/release-original/model.safetensors \
  /PATH/TO/release-onnx/manifest.json \
  /PATH/TO/release-onnx/model.onnx
kjnlae model verify --directory /PATH/TO/release-onnx \
  --hash 537899c45553fc6583587684c5685d57c159c1b9f387590b182e1ce0f9a9ea4c
export KJNLAE_MODEL_DIR=/PATH/TO/release-onnx
export KJNLAE_MODEL_HASH=537899c45553fc6583587684c5685d57c159c1b9f387590b182e1ce0f9a9ea4c
kjnlae doctor
printf '%s\n' 'Summarize the public schedule.' | kjnlae scan --source retrieved_document
```

Expected reference SHA-256 values: source manifest
`071f6166177efd4af978e46d2f44fae13fe1a4be8c2030c916c3b924ecfe4d61`,
weights `6c0896d72a1ef5bc5f49bd815412f8f66750055696ab716c6956ef872712c321`,
ONNX manifest
`537899c45553fc6583587684c5685d57c159c1b9f387590b182e1ce0f9a9ea4c`,
and ONNX graph
`aee933ab961a49d6c57ce0260220034b3e6e23177fc00602aa4e83578eb2106f`.
Install this branch from source until an application release and immutable
public model revision are approved. Normal model inference is offline.

## Publishing gate and rollback

Do **not** upload the model yet. The v0.3 Hugging Face repository name, if
approved, is `namelessweakling/kjnlae-distilbert-v0.3`. The release package
needs the entire `release-original` directory plus the reviewed
[candidate model card](model-card-v0.3-candidate.md) as the repository's
`README.md`. A local, **unpublished** Hugging Face staging directory already
exists at `/workspace/kjnlae-v03-work/hf-release-candidate`. It contains the
source model files, manifest, `README.md`, and the model card's linked
`reports/` files. Its source manifest still verifies as
`071f6166177efd4af978e46d2f44fae13fe1a4be8c2030c916c3b924ecfe4d61`.

After explicit publication approval, an authorized maintainer must use their
own Hugging Face CLI/OAuth credentials to create a **new** public repository,
upload that staging directory, then retrieve its immutable commit SHA. For
example, after reviewing the directory contents and authenticating locally:

```bash
hf repo create namelessweakling/kjnlae-distilbert-v0.3 --repo-type model
hf upload namelessweakling/kjnlae-distilbert-v0.3 /PATH/TO/hf-release-candidate . --repo-type model
python - <<'PY'
from huggingface_hub import HfApi
print(HfApi().model_info('namelessweakling/kjnlae-distilbert-v0.3').sha)
PY
```

These commands match the Hugging Face CLI available in the reference
environment; check permissions and repository visibility before uploading.
Download the immutable revision into a **fresh** local
directory, verify its manifest and every listed file, and record that
revision in a follow-up application release. Never replace v0.2 weights or make
`kjnlae model download` silently switch versions. The existing v0.2
installer remains the rollback path. Runtime opt-in to the local candidate
requires both exact `KJNLAE_MODEL_DIR` and `KJNLAE_MODEL_HASH`; removing
those variables returns to the installed public default when present.

## Private local backup awaiting transfer

The original and derived artifacts and reproducibility inputs were also
archived locally at
`/workspace/kjnlae-v03-work/v0.3-candidate-release-bundle.tar.zst`.
The archive is **494,088,831 bytes**, SHA-256
`e0e3b3e729690cb263ba0573b8b19aa12a41e2c60e5775548b0018edad3b6fbc`;
`zstd -t` and its adjacent `.sha256` check passed. It contains the complete
`release-original/` and `release-onnx/` directories, prepared splits and
input manifests under `data/`, the pinned public TRAIN downloads, probe/fit
reports, sealed selection and final results, model card, training guide,
frozen fixture, and machine-readable comparison and parity reports. The
archive is **not encrypted or uploaded**, and it is not in Git. The staging
directory can be rebuilt by copying the source model and these documents.
Transfer this backup privately before the cloud workspace expires; do not
publish the archive because it includes model weights and local prepared
training data. After restoring it on Fedora, run:

```bash
sha256sum -c v0.3-candidate-release-bundle.tar.zst.sha256
tar --zstd -tf v0.3-candidate-release-bundle.tar.zst
tar --zstd -xf v0.3-candidate-release-bundle.tar.zst
```
