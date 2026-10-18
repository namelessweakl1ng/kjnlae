"""A bounded real DistilBERT CPU optimization experiment."""

import hashlib
import json
import multiprocessing as mp
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from typing import Any, cast

from kjnlae.classifiers.artifacts import BASE_REVISION


@dataclass(frozen=True)
class ProbeConfig:
    base_dir: Path
    train_path: Path
    output_dir: Path
    seed: int = 42
    max_steps: int = 32
    deadline_s: int = 600

    def __post_init__(self) -> None:
        if not 1 <= self.max_steps <= 32 or not 1 <= self.deadline_s <= 600:
            raise ValueError("Probe must remain within 32 steps and 600 seconds")


def check_resources(worker_rss: int, cgroup: int, disk_free: int) -> bool:
    return worker_rss > 12 * 1024**3 or cgroup > 28 * 1024**3 or disk_free < 8 * 1024**3


def _worker_rss(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def _cgroup_bytes() -> int:
    try:
        return int(Path("/sys/fs/cgroup/memory.current").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0


def _tensor_digest(model: Any) -> str:
    digest = hashlib.sha256()
    for name, value in model.named_parameters():
        if name.startswith("distilbert.transformer.layer.0") or name.startswith("classifier"):
            digest.update(name.encode())
            digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def _probe_worker(config: ProbeConfig, rows: list[dict[str, Any]], queue: Any) -> None:
    try:
        os.environ["OMP_NUM_THREADS"] = "4"
        import torch
        from transformers.models.auto.configuration_auto import AutoConfig
        from transformers.models.auto.modeling_auto import AutoModelForSequenceClassification
        from transformers.models.auto.tokenization_auto import AutoTokenizer

        torch.manual_seed(config.seed)
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        started = time.monotonic()
        tokenizer = cast(Any, AutoTokenizer).from_pretrained(config.base_dir, local_files_only=True)
        model_config = AutoConfig.from_pretrained(config.base_dir, local_files_only=True)
        model_config.num_labels = 2
        model_config.id2label = {0: "NON_INJECTION", 1: "INJECTION"}
        model_config.label2id = {"NON_INJECTION": 0, "INJECTION": 1}
        model = (
            cast(Any, AutoModelForSequenceClassification)
            .from_pretrained(
                config.base_dir,
                config=model_config,
                local_files_only=True,
                use_safetensors=True,
                trust_remote_code=False,
            )
            .to("cpu")
            .train()
        )
        load_seconds = time.monotonic() - started
        before = _tensor_digest(model)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
        durations: list[float] = []
        losses: list[float] = []
        for step in range(config.max_steps):
            batch_rows = [rows[(step * 2 + item) % len(rows)] for item in range(2)]
            texts = [f"Source: {r['source']}\nContent:\n{r['text']}" for r in batch_rows]
            batch = tokenizer(
                texts, truncation=True, max_length=128, padding=True, return_tensors="pt"
            )
            labels = torch.tensor([r["label"] for r in batch_rows], dtype=torch.long)
            tick = time.monotonic()
            optimizer.zero_grad(set_to_none=True)
            loss = model(**batch, labels=labels).loss
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            loss.backward()
            gradient = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            if not torch.isfinite(gradient):
                raise ValueError("Non-finite gradient")
            optimizer.step()
            durations.append(time.monotonic() - tick)
            losses.append(float(loss.detach()))
            if time.monotonic() - started > config.deadline_s - 90:
                raise TimeoutError("Insufficient export/reload time remaining")
        after = _tensor_digest(model)
        if before == after:
            raise ValueError("Model parameters did not change")
        export_dir = config.output_dir / "experimental-probe"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_started = time.monotonic()
        model.save_pretrained(export_dir, safe_serialization=True)
        tokenizer.save_pretrained(export_dir)
        export_seconds = time.monotonic() - export_started
        reload_started = time.monotonic()
        reloaded = (
            cast(Any, AutoModelForSequenceClassification)
            .from_pretrained(
                export_dir, local_files_only=True, use_safetensors=True, trust_remote_code=False
            )
            .eval()
        )
        with torch.inference_mode():
            smoke = tokenizer("Source: webpage\nContent:\nExample", return_tensors="pt")
            shape = list(reloaded(**smoke).logits.shape)
        if shape != [1, 2]:
            raise ValueError("Reloaded model output shape is invalid")
        queue.put(
            {
                "status": "COMPLETE",
                "base_revision": BASE_REVISION,
                "steps": len(durations),
                "load_seconds": load_seconds,
                "warm_step_seconds": durations[:4],
                "steady_step_seconds": durations[4:],
                "losses": losses,
                "parameter_sha_before": before,
                "parameter_sha_after": after,
                "export_seconds": export_seconds,
                "reload_seconds": time.monotonic() - reload_started,
                "checkpoint_bytes": sum(
                    p.stat().st_size for p in export_dir.iterdir() if p.is_file()
                ),
                "total_seconds": time.monotonic() - started,
            }
        )
    except Exception as exc:
        queue.put({"status": "INCOMPLETE", "reason": type(exc).__name__, "detail": str(exc)[:160]})


def run_probe(config: ProbeConfig) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in config.train_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if any(row.get("split") != "TRAIN" for row in rows):
        raise ValueError("Probe requires TRAIN examples only")
    if len(rows) < 64:
        raise ValueError("Probe requires at least 64 TRAIN examples")
    rows = rows[:64]
    if {row.get("label") for row in rows} != {0, 1}:
        raise ValueError("Probe subset must contain both classes")
    if not config.base_dir.joinpath("model.safetensors").is_file():
        raise ValueError("Verified base model is missing")
    if check_resources(0, _cgroup_bytes(), shutil.disk_usage(config.output_dir.parent).free):
        raise ValueError("Insufficient resources for bounded probe")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_probe_worker, args=(config, rows, queue))
    process.start()
    started = time.monotonic()
    max_rss = 0
    max_cgroup = 0
    stop_reason = ""
    while process.is_alive():
        elapsed = time.monotonic() - started
        rss = _worker_rss(process.pid or 0)
        cgroup = _cgroup_bytes()
        free = shutil.disk_usage(config.output_dir).free
        max_rss = max(max_rss, rss)
        max_cgroup = max(max_cgroup, cgroup)
        if elapsed >= config.deadline_s:
            stop_reason = "WALL_DEADLINE"
            break
        if check_resources(rss, cgroup, free):
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
            "stop_reason": stop_reason,
            "peak_worker_rss_bytes": max_rss,
            "peak_cgroup_bytes": max_cgroup,
            "parent_wall_seconds": time.monotonic() - started,
            "worker_exit_code": process.exitcode,
            "train_example_count": len(rows),
            "seed": config.seed,
            "cpu_threads": 4,
            "batch_size": 2,
            "max_tokens": 128,
        }
    )
    if report["status"] != "COMPLETE":
        shutil.rmtree(config.output_dir / "experimental-probe", ignore_errors=True)
    (config.output_dir / "probe-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    queue.close()
    return report
