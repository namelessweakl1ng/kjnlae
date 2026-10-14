"""Bounded full-encoder CPU fine-tuning with validation-only checkpoint selection."""

import hashlib
import json
import math
import multiprocessing as mp
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty
from typing import Any, cast

from kjnlae.classifiers.artifacts import BASE_REVISION
from kjnlae.training.probe import _cgroup_bytes, _worker_rss, check_resources


@dataclass(frozen=True)
class FitConfig:
    base_dir: Path
    train_path: Path
    validation_path: Path
    output_dir: Path
    seed: int = 42
    epochs: int = 4
    max_tokens: int = 128
    batch_size: int = 2
    learning_rate: float = 2e-5
    patience: int = 2
    deadline_s: int = 300

    def __post_init__(self) -> None:
        if (
            not 1 <= self.epochs <= 4
            or self.max_tokens != 128
            or self.batch_size != 2
            or not 0 < self.learning_rate <= 1e-4
            or not 1 <= self.patience <= 3
            or not 1 <= self.deadline_s <= 600
        ):
            raise ValueError("Fit configuration exceeds measured CPU limits")


def class_weights(labels: list[int]) -> tuple[float, float]:
    if not labels or set(labels) != {0, 1}:
        raise ValueError("Both classes are required in TRAIN")
    return (len(labels) / (2 * labels.count(0)), len(labels) / (2 * labels.count(1)))


def validate_partitions(
    train: Path, validation: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    for path, expected in ((train, "TRAIN"), (validation, "VALIDATION")):
        items = [json.loads(line) for line in path.read_text().splitlines() if line]
        if not items or any(row.get("split") != expected for row in items):
            raise ValueError(f"{expected} partition contains wrong or no rows")
        rows.append(items)
    if {r["id"] for r in rows[0]} & {r["id"] for r in rows[1]}:
        raise ValueError("TRAIN/VALIDATION example leakage")
    return rows[0], rows[1]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _worker(
    cfg: FitConfig, train: list[dict[str, Any]], validation: list[dict[str, Any]], queue: Any
) -> None:
    try:
        os.environ["OMP_NUM_THREADS"] = "4"
        import torch
        from transformers.models.auto.configuration_auto import AutoConfig
        from transformers.models.auto.modeling_auto import AutoModelForSequenceClassification
        from transformers.models.auto.tokenization_auto import AutoTokenizer

        started = time.monotonic()
        torch.manual_seed(cfg.seed)
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        tokenizer = cast(Any, AutoTokenizer).from_pretrained(cfg.base_dir, local_files_only=True)
        model_config = AutoConfig.from_pretrained(cfg.base_dir, local_files_only=True)
        model_config.num_labels = 2
        model_config.id2label = {0: "NON_INJECTION", 1: "INJECTION"}
        model_config.label2id = {"NON_INJECTION": 0, "INJECTION": 1}
        model = (
            cast(Any, AutoModelForSequenceClassification)
            .from_pretrained(
                cfg.base_dir,
                config=model_config,
                local_files_only=True,
                use_safetensors=True,
                trust_remote_code=False,
            )
            .to("cpu")
        )
        initial_dir = cfg.output_dir / "initial-control"
        initial_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(initial_dir, safe_serialization=True)
        tokenizer.save_pretrained(initial_dir)
        before_hash = _digest(initial_dir / "model.safetensors")
        weights = class_weights([r["label"] for r in train])
        criterion = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights))
        optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
        steps_per_epoch = math.ceil(len(train) / cfg.batch_size)
        total_steps = steps_per_epoch * cfg.epochs
        warmup = max(1, total_steps // 10)

        def lr_factor(step: int) -> float:
            if step < warmup:
                return max(0.1, (step + 1) / warmup)
            return max(0.01, (total_steps - step) / max(1, total_steps - warmup))

        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_factor)
        generator = torch.Generator().manual_seed(cfg.seed)
        history: list[dict[str, float | int]] = []
        best_f1 = -1.0
        best_loss = float("inf")
        best_epoch = 0
        stale = 0
        steps = 0
        for epoch in range(1, cfg.epochs + 1):
            model.train()
            order = torch.randperm(len(train), generator=generator).tolist()
            train_losses: list[float] = []
            for start in range(0, len(order), cfg.batch_size):
                batch_rows = [train[i] for i in order[start : start + cfg.batch_size]]
                texts = [f"Source: {r['source']}\nContent:\n{r['text']}" for r in batch_rows]
                batch = tokenizer(
                    texts,
                    max_length=cfg.max_tokens,
                    truncation=True,
                    padding=True,
                    return_tensors="pt",
                )
                labels = torch.tensor([r["label"] for r in batch_rows], dtype=torch.long)
                optimizer.zero_grad(set_to_none=True)
                logits = model(**batch).logits
                loss = criterion(logits, labels)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                loss.backward()
                grad = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                if not torch.isfinite(grad):
                    raise ValueError("Non-finite training gradient")
                optimizer.step()
                scheduler.step()
                steps += 1
                train_losses.append(float(loss.detach()))
                if time.monotonic() - started > cfg.deadline_s - 30:
                    raise TimeoutError("Insufficient checkpoint time remaining")
            model.eval()
            truth: list[int] = []
            predicted: list[int] = []
            validation_losses: list[float] = []
            with torch.inference_mode():
                for row in validation:
                    text = f"Source: {row['source']}\nContent:\n{row['text']}"
                    batch = tokenizer(
                        text, max_length=cfg.max_tokens, truncation=True, return_tensors="pt"
                    )
                    logits = model(**batch).logits
                    validation_losses.append(float(criterion(logits, torch.tensor([row["label"]]))))
                    score = float(torch.softmax(logits, dim=-1)[0, 1])
                    truth.append(row["label"])
                    predicted.append(int(score >= 0.5))
            tp = sum(p == y == 1 for p, y in zip(predicted, truth, strict=True))
            fp = sum(p == 1 and y == 0 for p, y in zip(predicted, truth, strict=True))
            fn = sum(p == 0 and y == 1 for p, y in zip(predicted, truth, strict=True))
            f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
            val_loss = sum(validation_losses) / len(validation_losses)
            history.append(
                {
                    "epoch": epoch,
                    "steps": steps,
                    "train_loss": sum(train_losses) / len(train_losses),
                    "validation_loss": val_loss,
                    "validation_f1_at_0_5": f1,
                }
            )
            if f1 > best_f1 or (f1 == best_f1 and val_loss < best_loss):
                best_f1, best_loss, best_epoch, stale = f1, val_loss, epoch, 0
                best_dir = cfg.output_dir / "best"
                best_dir.mkdir(parents=True, exist_ok=True)
                model.save_pretrained(best_dir, safe_serialization=True)
                tokenizer.save_pretrained(best_dir)
            else:
                stale += 1
                if stale >= cfg.patience:
                    break
        best_hash = _digest(cfg.output_dir / "best" / "model.safetensors")
        if before_hash == best_hash:
            raise ValueError("Encoder/head weights did not update")
        queue.put(
            {
                "status": "COMPLETE",
                "base_revision": BASE_REVISION,
                "epochs_completed": len(history),
                "steps": steps,
                "best_epoch": best_epoch,
                "best_validation_f1_at_0_5": best_f1,
                "best_validation_loss": best_loss,
                "history": history,
                "train_count": len(train),
                "validation_count": len(validation),
                "class_weights": weights,
                "initial_weight_sha256": before_hash,
                "best_weight_sha256": best_hash,
                "worker_seconds": time.monotonic() - started,
            }
        )
    except Exception as exc:
        queue.put({"status": "INCOMPLETE", "reason": type(exc).__name__, "detail": str(exc)[:160]})


def fit(config: FitConfig) -> dict[str, Any]:
    train, validation = validate_partitions(config.train_path, config.validation_path)
    if not config.base_dir.joinpath("model.safetensors").is_file():
        raise ValueError("Approved base model is missing")
    if check_resources(0, _cgroup_bytes(), shutil.disk_usage(config.output_dir.parent).free):
        raise ValueError("Insufficient resources for full CPU training")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(target=_worker, args=(config, train, validation, queue))
    process.start()
    started = time.monotonic()
    max_rss = 0
    max_cgroup = 0
    stop_reason = ""
    while process.is_alive():
        max_rss = max(max_rss, _worker_rss(process.pid or 0))
        max_cgroup = max(max_cgroup, _cgroup_bytes())
        if time.monotonic() - started > config.deadline_s:
            stop_reason = "WALL_DEADLINE"
            break
        if check_resources(max_rss, max_cgroup, shutil.disk_usage(config.output_dir).free):
            stop_reason = "RESOURCE_LIMIT"
            break
        process.join(timeout=0.5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
    try:
        report = queue.get(timeout=1) if not stop_reason else {"status": "INCOMPLETE"}
    except Empty:
        report = {"status": "INCOMPLETE", "reason": "WORKER_EXIT"}
    report.update(
        {
            "config": {
                **asdict(config),
                **{
                    key: str(getattr(config, key))
                    for key in ("base_dir", "train_path", "validation_path", "output_dir")
                },
            },
            "train_sha256": _digest(config.train_path),
            "validation_sha256": _digest(config.validation_path),
            "stop_reason": stop_reason,
            "peak_worker_rss_bytes": max_rss,
            "peak_cgroup_bytes": max_cgroup,
            "parent_wall_seconds": time.monotonic() - started,
            "worker_exit_code": process.exitcode,
        }
    )
    if report["status"] != "COMPLETE":
        shutil.rmtree(config.output_dir / "best", ignore_errors=True)
    (config.output_dir / "fit-report.json").write_text(json.dumps(report, indent=2) + "\n")
    queue.close()
    return report
