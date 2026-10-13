# Publish and download the v0.2 experimental model

The application source and the reviewed model weights are separate artifacts. No public installation can perform model-only scanning until the verified weights are explicitly downloaded. **Do not upload the encrypted training backups or raw public-source datasets.**

The owner already verified the v3-reviewed artifact on Fedora:

- Model path: `~/kjnlae-v3-restore/var/models/full-v0.2-v3-reviewed/`
- Manifest SHA-256: `54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b`
- Full archive and separate private encrypted backups remain offline/private.

## 1. Publisher: review before publication

Read [the model card](model-card-v0.2.md) and [the data-provenance record](model-data.md). The model card **proposes Apache-2.0 licensing for the weights** in line with the base model; confirm you're comfortable licensing your own fine-tuned weights on those terms. The training set included Microsoft BIPIA and Deepset, and Deepset has conflicting Apache-2.0 / CC BY 4.0 declarations. Retain copyright, source credits and notices, and seek further review if required for your use case. There is no raw third-party dataset in the published file list.

The release is **experimental**, with serious false positives. It is not production-ready protection or a guarantee that an AI agent will resist prompt injections.

## 2. Publisher: prepare on Fedora

Run these steps in a clean clone of the model-publication branch. Use your own Hugging Face account's **write** token; do not paste it into issues, chat, source code, or shell history.

```bash
git clone --branch feat/public-model-hub \
  https://github.com/namelessweakl1ng/kjnlae.git ~/kjnlae-publication
cd ~/kjnlae-publication
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install 'huggingface_hub>=0.34,<1'
hf auth login
hf auth whoami
```

If your installed Hub CLI doesn't expose `hf`, use `huggingface-cli login` instead, or update the Hub client.

Now inspect the inventory **without uploading anything**:

```bash
python scripts/publish_model.py \
  --model-dir "$HOME/kjnlae-v3-restore/var/models/full-v0.2-v3-reviewed"
```

The list should contain `model.safetensors`, the tokenizer/configuration files listed in the verified manifest, `manifest.json` and the generated `README.md` model card. There should be no training JSONL/parquet, backup archive, report, identity key or token.

After you have approved the model license and attribution, create a **new public model repository** and upload just those files:

```bash
python scripts/publish_model.py \
  --model-dir "$HOME/kjnlae-v3-restore/var/models/full-v0.2-v3-reviewed" \
  --publish
```

The script reads your authenticated Hugging Face username, targets `USERNAME/kjnlae-distilbert-v0.2`, prints the final public destination, and asks you to type `PUBLISH` before creating/uploading. It refuses to overwrite an already-existing model repository. It prints the final Hub commit SHA; record that revision for a reproducible install.

## 3. Everyone else: verified download

Once the model repository is published, install the application (following [the Fedora or Linux instructions](../README.md)), then:

```bash
python -m pip install 'huggingface_hub>=0.30,<1'
kjnlae model download \
  --repo YOUR_HF_USERNAME/kjnlae-distilbert-v0.2 \
  --revision THE_PUBLISHED_HF_COMMIT_SHA

export KJNLAE_MODEL_DIR="$PWD/var/models/full-v0.2-v3-reviewed"
export KJNLAE_MODEL_HASH="54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b"

kjnlae model verify "$KJNLAE_MODEL_DIR" --hash "$KJNLAE_MODEL_HASH"
kjnlae doctor
kjnlae serve
```

For development, the optional `--revision` defaults to `main`, but using the exact Hub commit SHA is more reproducible. The downloader pins the manifest hash (overridable only explicitly with `--hash`), checks each file's SHA-256, downloads only files in the manifest, installs from an isolated staging folder, and will not overwrite an existing model directory. **Runtime scan and API startup never contact the Hub.**

If you already restored the model manually from the private backup, do not run the downloader into that same directory. Simply set the two environment variables above and run `kjnlae doctor`.

## 4. Public model smoke test

From a *different*, empty destination, verify a real public download:

```bash
kjnlae model download \
  --repo YOUR_HF_USERNAME/kjnlae-distilbert-v0.2 \
  --revision THE_PUBLISHED_HF_COMMIT_SHA \
  --directory var/models/hub-smoke-v0.2

KJNLAE_MODEL_DIR="$PWD/var/models/hub-smoke-v0.2" \
KJNLAE_MODEL_HASH="54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b" \
  kjnlae doctor
```

Only after that smoke test should the README link the *actual* Hugging Face model page and exact revision.

This publication step does **not** publish to PyPI. Users currently install the Python source from GitHub; providing a public model and verified downloader makes that GitHub installation usable.
