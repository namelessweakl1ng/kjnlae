"""Real optional CPU Transformers inference in a deadline-bound process.

No remote code, no weights in this package. Download explicitly after license review.
"""

import multiprocessing as mp
import re
import threading
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

from kjnlae.schemas import Classification


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
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

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
        with self._lock:
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
                    if not parent.poll(self.config.timeout):
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
                if not self._conn.poll(self.config.timeout):
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

    def provenance(self) -> dict[str, Any]:
        return {**asdict(self.config), "status": self.status, "device": "cpu"}
