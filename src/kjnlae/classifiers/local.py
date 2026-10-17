"""Bounded CPU inference from verified local fine-tuned model artifacts."""

import multiprocessing as mp
import re
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Protocol

from kjnlae.classifiers.artifacts import verify_onnx_artifact
from kjnlae.detection.preprocessing import InspectionView
from kjnlae.schemas import Source
from kjnlae.schemas_v2 import ModelStatus


class _WorkerPipe(Protocol):
    """Methods shared by POSIX Connection and Windows PipeConnection."""

    def send(self, obj: Any) -> None: ...

    def recv(self) -> Any: ...

    def poll(self, timeout: float = 0.0) -> bool: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ModelWindow:
    """One scored token window mapped to offsets in the original input."""

    view: str
    source_span: tuple[int, int]
    score: float | None = None


@dataclass(frozen=True)
class LocalInference:
    """Worker result; incomplete status must never be treated as a clear scan."""

    status: ModelStatus
    inspection_complete: bool
    score: float | None = None
    windows: tuple[ModelWindow, ...] = ()
    reason: str = ""
    model_hash: str | None = None


@dataclass(frozen=True)
class LocalModelConfig:
    """Bounds for local CPU inference and the pinned model artifact."""

    model_dir: Path
    manifest_hash: str
    token_limit: int = 128
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


def window_ranges(length: int, width: int, overlap: int) -> tuple[tuple[int, int], ...]:
    """Cover all tokens with overlapping windows, including the final tail."""
    if length < 0 or width <= 0 or overlap < 0 or overlap >= width:
        raise ValueError("Invalid window bounds")
    if length == 0:
        return ((0, 0),)
    spans: list[tuple[int, int]] = []
    for start in range(0, length, width - overlap):
        end = min(length, start + width)
        spans.append((start, end))
        if end == length:
            break
    return tuple(spans)


def build_windows(
    views: Sequence[InspectionView],
    tokenized: Sequence[Sequence[tuple[int, int]]],
    width: int,
    overlap: int,
    max_windows: int,
) -> tuple[ModelWindow, ...] | None:
    """Map every token window back to source offsets, or reject excess coverage."""
    if width <= 0 or overlap < 0 or overlap >= width or len(views) != len(tokenized):
        raise ValueError("Invalid token windows")
    result: list[ModelWindow] = []
    for view, offsets in zip(views, tokenized, strict=True):
        if len(offsets) == 0:
            result.append(ModelWindow(view.name, (0, 0)))
            continue
        for start, end in window_ranges(len(offsets), width, overlap):
            first, last = offsets[start][0], offsets[end - 1][1]
            if first < 0 or last > len(view.mapping) or first >= last:
                raise ValueError("Invalid token-to-source mapping")
            result.append(
                ModelWindow(view.name, (view.mapping[first][0], view.mapping[last - 1][1]))
            )
            if len(result) > max_windows:
                return None
    return tuple(result)


def _scores_from_logits(logits: Any) -> list[float]:
    """Reject invalid model output before it reaches the policy decision."""
    import numpy as np

    if logits.ndim != 2 or logits.shape[1] != 2 or not np.isfinite(logits).all():
        raise ValueError("Invalid model logits")
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    probabilities = exp[:, 1] / np.sum(exp, axis=1)
    if not np.isfinite(probabilities).all():
        raise ValueError("Invalid model logits")
    return [float(value) for value in probabilities]


def _local_worker(conn: _WorkerPipe, cfg: LocalModelConfig) -> None:
    """Load only the verified CPU graph, then score every bounded view/window."""
    try:
        import os

        os.environ["OMP_NUM_THREADS"] = "4"
        # RLIMIT_AS is Linux-specific in practical use. Spawn and the hard
        # inference deadline remain active on Windows and macOS.
        if sys.platform == "linux":
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (cfg.memory_mb * 1024**2,) * 2)
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        artifact = verify_onnx_artifact(cfg.model_dir, cfg.manifest_hash)
        tokenizer = Tokenizer.from_file(str(cfg.model_dir / "tokenizer.json"))
        # The exported tokenizer.json embeds a 128-token truncation setting.
        # Disable it so our own bounded overlapping windows cover every token.
        tokenizer.no_truncation()
        tokenizer.no_padding()
        cls_id, sep_id = tokenizer.token_to_id("[CLS]"), tokenizer.token_to_id("[SEP]")
        if cls_id is None or sep_id is None:
            raise ValueError("Verified tokenizer lacks special tokens")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        model = ort.InferenceSession(
            str(cfg.model_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        conn.send({"loaded": True})
        while True:
            message = conn.recv()
            if message is None:
                break
            views, source = message
            prefix_ids = tokenizer.encode(
                f"Source: {source}\nContent:\n", add_special_tokens=False
            ).ids
            width = cfg.token_limit - 2 - len(prefix_ids)
            if width < 8:
                conn.send({"status": "ERROR", "reason": "TOKEN_LIMIT_TOO_LOW"})
                continue
            encodings = [tokenizer.encode(v.text, add_special_tokens=False) for v in views]
            offsets = [e.offsets for e in encodings]
            specs = build_windows(views, offsets, width, cfg.overlap, cfg.max_windows)
            if specs is None:
                conn.send({"status": "ERROR", "reason": "COVERAGE_EXCEEDED"})
                continue
            batches: list[list[int]] = []
            for encoding in encodings:
                ids = encoding.ids
                if not ids:
                    batches.append(prefix_ids)
                    continue
                for start, end in window_ranges(len(ids), width, cfg.overlap):
                    batches.append(prefix_ids + ids[start:end])
            scores: list[float] = []
            for pos in range(0, len(batches), cfg.batch_size):
                ready = [[cls_id, *ids, sep_id] for ids in batches[pos : pos + cfg.batch_size]]
                size = max(map(len, ready))
                ids_array = np.zeros((len(ready), size), dtype=np.int64)
                mask_array = np.zeros_like(ids_array)
                for row, ids in enumerate(ready):
                    ids_array[row, : len(ids)] = ids
                    mask_array[row, : len(ids)] = 1
                logits = model.run(
                    ["logits"], {"input_ids": ids_array, "attention_mask": mask_array}
                )[0]
                scores.extend(_scores_from_logits(logits))
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
        self._conn: _WorkerPipe | None = None
        self._lock = threading.Lock()

    def close(self) -> None:
        """Terminate the worker and release its pipe; safe to call repeatedly."""
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
        """Whether an already-started worker is alive; this does not load it."""
        return self._process is not None and self._process.is_alive()

    def classify_views(self, views: Sequence[InspectionView], source: Source) -> LocalInference:
        """Run a complete timed scan or return an explicit unavailable status."""
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
        """Worker cleanup for callers that already hold the classifier lock."""
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
