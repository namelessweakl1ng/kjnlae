"""Real optional CPU Transformers inference in a deadline-bound process.

No remote code, no weights in this package. Download explicitly after license review.
"""

import multiprocessing as mp
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import verify_artifact
from kjnlae.detection.preprocessing import InspectionView
from kjnlae.schemas import Classification, Source


@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    revision: str
    positive_label: str
    token_limit: int = 256
    overlap: int = 32
    max_windows: int = 128
    batch_size: int = 8
    timeout: float = 30
    memory_mb: int = 8192
    local_files_only: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-fA-F0-9]{40}", self.revision):
            raise ValueError("Pin an exact 40-character model commit revision")
        if not self.model_id or not self.positive_label:
            raise ValueError("Model ID and explicit positive label required")
        if not (
            32 <= self.token_limit <= 512
            and 0 <= self.overlap < self.token_limit - 8
            and 1 <= self.max_windows <= 256
            and 1 <= self.batch_size <= 16
            and 0 < self.timeout <= 300
            and 2048 <= self.memory_mb <= 32768
        ):
            raise ValueError("Invalid inference resource limits")


def _worker(conn: Connection, cfg: ModelConfig) -> None:
    try:
        import os
        import resource

        os.environ["OMP_NUM_THREADS"] = "1"
        resource.setrlimit(resource.RLIMIT_AS, (cfg.memory_mb * 1024**2, cfg.memory_mb * 1024**2))
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore[attr-defined]

        torch.set_num_threads(1)
        tokenizer = AutoTokenizer.from_pretrained(
            cfg.model_id,
            revision=cfg.revision,
            trust_remote_code=False,
            local_files_only=cfg.local_files_only,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            cfg.model_id,
            revision=cfg.revision,
            trust_remote_code=False,
            local_files_only=cfg.local_files_only,
            use_safetensors=True,
        )
        model.to("cpu").eval()
        labels = {str(v): int(k) for k, v in model.config.id2label.items()}
        if cfg.positive_label not in labels:
            raise ValueError("Configured positive label absent from model id2label")
        positive = labels[cfg.positive_label]
        conn.send({"loaded": True})
        while True:
            text = conn.recv()
            if text is None:
                break
            ids = tokenizer.encode(text, add_special_tokens=False, truncation=False)
            width = cfg.token_limit - tokenizer.num_special_tokens_to_add(pair=False)
            stride = width - cfg.overlap
            windows = [ids[i : i + width] for i in range(0, max(1, len(ids)), stride)]
            if len(windows) > cfg.max_windows:
                conn.send({"status": "coverage_exceeded", "detail": "Token window budget exceeded"})
                continue
            scores: list[float] = []
            for i in range(0, len(windows), cfg.batch_size):
                encoded = [
                    tokenizer.prepare_for_model(
                        w, add_special_tokens=True, return_attention_mask=True
                    )
                    for w in windows[i : i + cfg.batch_size]
                ]
                batch = tokenizer.pad(encoded, padding=True, return_tensors="pt")
                with torch.inference_mode():
                    probabilities = torch.softmax(model(**batch).logits, dim=-1)[:, positive]
                scores.extend(probabilities.tolist())
            conn.send({"status": "available", "score": max(scores), "windows": len(windows)})
    except Exception:
        # Avoid leaking local paths, tokens or model downloader messages through API.
        try:
            conn.send(
                {
                    "status": "unavailable",
                    "detail": "Model dependencies, weights or label unavailable",
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        conn.close()


class TransformersClassifier:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._process: BaseProcess | None = None
        self._conn: Connection | None = None
        self._lock = threading.Lock()
        self.status = "not_loaded"

    def _stop(self) -> None:
        if self._process:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=1)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1)
        if self._conn:
            self._conn.close()
        self._process, self._conn = None, None

    def close(self) -> None:
        with self._lock:
            self._stop()

    def classify(self, text: str) -> Classification:
        if not text or len(text) > 32768:
            raise ValueError("Classifier input exceeds bounds")
        if not self._lock.acquire(blocking=False):
            return Classification(
                status="unavailable",
                detail="Inference worker busy",
                model_id=self.config.model_id,
                revision=self.config.revision,
            )
        try:
            return self._classify_locked(text)
        finally:
            self._lock.release()

    def _classify_locked(self, text: str) -> Classification:
        deadline = time.monotonic() + self.config.timeout
        try:
            if not self._process or not self._process.is_alive():
                self._stop()
                parent, child = mp.get_context("spawn").Pipe()
                self._conn = parent
                self._process = mp.get_context("spawn").Process(
                    target=_worker, args=(child, self.config), daemon=True
                )
                self._process.start()
                child.close()
                if not parent.poll(max(0, deadline - time.monotonic())):
                    raise TimeoutError
                loaded = parent.recv()
                if not loaded.get("loaded"):
                    self.status = "unavailable"
                    self._stop()
                    return Classification(
                        **loaded, model_id=self.config.model_id, revision=self.config.revision
                    )
            assert self._conn is not None
            self._conn.send(text)
            if not self._conn.poll(max(0, deadline - time.monotonic())):
                raise TimeoutError
            result: dict[str, Any] = self._conn.recv()
            self.status = str(result["status"])
            return Classification(
                **result, model_id=self.config.model_id, revision=self.config.revision
            )
        except TimeoutError:
            self.status = "timeout"
            self._stop()
            return Classification(
                status="timeout",
                model_id=self.config.model_id,
                revision=self.config.revision,
                detail="Worker deadline exceeded",
            )
        except (EOFError, OSError, ValueError):
            self.status = "error"
            self._stop()
            return Classification(
                status="error",
                detail="Model worker failed",
                model_id=self.config.model_id,
                revision=self.config.revision,
            )

    def is_ready(self) -> bool:
        return self.status == "available" and self._process is not None and self._process.is_alive()

    def provenance(self) -> dict[str, Any]:
        return {**asdict(self.config), "status": self.status, "device": "cpu"}


@dataclass(frozen=True)
class ModelWindow:
    view: str
    source_span: tuple[int, int]
    score: float | None = None


@dataclass(frozen=True)
class LocalInference:
    status: str
    inspection_complete: bool
    score: float | None = None
    windows: tuple[ModelWindow, ...] = ()
    reason: str = ""
    model_hash: str | None = None


@dataclass(frozen=True)
class LocalModelConfig:
    model_dir: Path
    manifest_hash: str
    token_limit: int = 256
    overlap: int = 32
    max_windows: int = 128
    batch_size: int = 8
    timeout: float = 45
    memory_mb: int = 12288

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-f0-9]{64}", self.manifest_hash)
            or not 32 <= self.token_limit <= 512
            or not 0 <= self.overlap < self.token_limit - 8
            or not 1 <= self.max_windows <= 256
            or not 1 <= self.batch_size <= 16
            or not 0 < self.timeout <= 300
            or not 2048 <= self.memory_mb <= 24576
        ):
            raise ValueError("Invalid local model configuration")


def build_windows(
    views: Sequence[InspectionView],
    tokenized: Sequence[Sequence[tuple[int, int]]],
    width: int,
    overlap: int,
    max_windows: int,
) -> tuple[ModelWindow, ...] | None:
    if width <= 0 or overlap < 0 or overlap >= width or len(views) != len(tokenized):
        raise ValueError("Invalid token windows")
    result: list[ModelWindow] = []
    for view, offsets in zip(views, tokenized, strict=True):
        if len(offsets) == 0:
            result.append(ModelWindow(view.name, (0, 0)))
            continue
        for start in range(0, len(offsets), width - overlap):
            end = min(len(offsets), start + width)
            first, last = offsets[start][0], offsets[end - 1][1]
            if first < 0 or last > len(view.mapping) or first >= last:
                raise ValueError("Invalid token-to-source mapping")
            result.append(
                ModelWindow(view.name, (view.mapping[first][0], view.mapping[last - 1][1]))
            )
            if len(result) > max_windows:
                return None
            if end == len(offsets):
                break
    return tuple(result)


def _local_worker(conn: Connection, cfg: LocalModelConfig) -> None:
    try:
        import os
        import resource

        os.environ["OMP_NUM_THREADS"] = "4"
        resource.setrlimit(resource.RLIMIT_AS, (cfg.memory_mb * 1024**2,) * 2)
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore[attr-defined]

        artifact = verify_artifact(cfg.model_dir, cfg.manifest_hash)
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        tokenizer = AutoTokenizer.from_pretrained(
            cfg.model_dir, local_files_only=True, trust_remote_code=False, use_fast=True
        )
        model = (
            AutoModelForSequenceClassification.from_pretrained(
                cfg.model_dir, local_files_only=True, trust_remote_code=False, use_safetensors=True
            )
            .to("cpu")
            .eval()
        )
        conn.send({"loaded": True})
        while True:
            message = conn.recv()
            if message is None:
                break
            views, source = message
            prefix_ids = tokenizer.encode(f"Source: {source}\nContent:\n", add_special_tokens=False)
            width = (
                cfg.token_limit - tokenizer.num_special_tokens_to_add(pair=False) - len(prefix_ids)
            )
            if width < 8:
                conn.send({"status": "ERROR", "reason": "TOKEN_LIMIT_TOO_LOW"})
                continue
            encodings = [
                tokenizer(v.text, add_special_tokens=False, return_offsets_mapping=True)
                for v in views
            ]
            offsets = [e["offset_mapping"] for e in encodings]
            specs = build_windows(views, offsets, width, cfg.overlap, cfg.max_windows)
            if specs is None:
                conn.send({"status": "ERROR", "reason": "COVERAGE_EXCEEDED"})
                continue
            batches: list[list[int]] = []
            for encoding in encodings:
                ids = encoding["input_ids"]
                if not ids:
                    batches.append(prefix_ids)
                    continue
                for start in range(0, len(ids), width - cfg.overlap):
                    end = min(len(ids), start + width)
                    batches.append(prefix_ids + ids[start:end])
                    if end == len(ids):
                        break
            scores: list[float] = []
            for pos in range(0, len(batches), cfg.batch_size):
                ready = [
                    tokenizer.prepare_for_model(ids, add_special_tokens=True)
                    for ids in batches[pos : pos + cfg.batch_size]
                ]
                batch = tokenizer.pad(ready, padding=True, return_tensors="pt")
                with torch.inference_mode():
                    probabilities = torch.softmax(model(**batch).logits, dim=-1)[:, 1]
                scores.extend(float(value) for value in probabilities.tolist())
            if len(scores) != len(specs):
                conn.send({"status": "ERROR", "reason": "WINDOW_COUNT_MISMATCH"})
                continue
            conn.send(
                {
                    "status": "AVAILABLE",
                    "score": max(scores),
                    "model_hash": artifact.sha256,
                    "windows": [
                        {"view": spec.view, "source_span": spec.source_span, "score": score}
                        for spec, score in zip(specs, scores, strict=True)
                    ],
                }
            )
    except Exception:
        try:
            conn.send({"status": "ERROR", "reason": "MODEL_WORKER_FAILED"})
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        conn.close()


class LocalClassifier:
    """Only verified local fine-tuned artifacts are accepted as a detector."""

    def __init__(self, config: LocalModelConfig) -> None:
        self.config = config
        self._process: BaseProcess | None = None
        self._conn: Connection | None = None
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._process is not None:
                if self._process.is_alive():
                    self._process.terminate()
                self._process.join(timeout=1)
                if self._process.is_alive():
                    self._process.kill()
                    self._process.join(timeout=1)
            if self._conn is not None:
                self._conn.close()
            self._process, self._conn = None, None

    def is_ready(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def classify_views(self, views: Sequence[InspectionView], source: Source) -> LocalInference:
        if not self.config.model_dir.exists():
            return LocalInference("MISSING", False, reason="MODEL_MISSING")
        if not self._lock.acquire(blocking=False):
            return LocalInference("UNAVAILABLE", False, reason="MODEL_BUSY")
        try:
            return self._classify_locked(views, source)
        finally:
            self._lock.release()

    def _classify_locked(self, views: Sequence[InspectionView], source: Source) -> LocalInference:
        deadline = time.monotonic() + self.config.timeout
        try:
            if self._process is None or not self._process.is_alive():
                self.close_unlocked()
                parent, child = mp.get_context("spawn").Pipe()
                self._conn = parent
                self._process = mp.get_context("spawn").Process(
                    target=_local_worker, args=(child, self.config), daemon=True
                )
                self._process.start()
                child.close()
                if not parent.poll(max(0, deadline - time.monotonic())):
                    raise TimeoutError
                loaded = parent.recv()
                if not loaded.get("loaded"):
                    self.close_unlocked()
                    return LocalInference("CORRUPTED", False, reason=str(loaded.get("reason")))
            assert self._conn is not None
            self._conn.send((tuple(views), source))
            if not self._conn.poll(max(0, deadline - time.monotonic())):
                raise TimeoutError
            result = self._conn.recv()
            if result.get("status") != "AVAILABLE":
                return LocalInference("ERROR", False, reason=str(result.get("reason")))
            windows = tuple(ModelWindow(**entry) for entry in result["windows"])
            return LocalInference(
                "AVAILABLE", True, result["score"], windows, model_hash=result["model_hash"]
            )
        except TimeoutError:
            self.close_unlocked()
            return LocalInference("TIMED_OUT", False, reason="MODEL_TIMEOUT")
        except (EOFError, OSError, ValueError):
            self.close_unlocked()
            return LocalInference("ERROR", False, reason="MODEL_WORKER_FAILED")

    def close_unlocked(self) -> None:
        if self._process is not None:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=1)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1)
        if self._conn is not None:
            self._conn.close()
        self._process, self._conn = None, None
