"""Import BIPIA builder exports, not redistributed upstream data.

Callers must review upstream context licenses. Import does not measure LLM ASR.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def import_export(path: Path) -> list[dict[str, Any]]:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Export exceeds 16 MiB")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cases = []
    for i, line in enumerate(raw.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        record = json.loads(line)
        text = record.get("context")
        if not isinstance(text, str) or not 1 <= len(text) <= 32768:
            raise ValueError(f"Row {i}: expected bounded poisoned context string")
        explicit = record.get("attack")
        if type(explicit) is bool:
            label = explicit
        elif isinstance(record.get("attack_name"), str) and record.get("attack_str"):
            label = True
        else:
            raise ValueError(f"Row {i}: explicit label or BIPIA attack metadata required")
        cases.append(
            {
                "id": f"bipia-{i}",
                "text": text,
                "attack": label,
                "source": "retrieved_document",
                "purpose": "reference",
                "category": str(record.get("attack_name", "benign")),
                "provenance": {
                    "adapter": "BIPIA-builder-export",
                    "export_sha256": digest,
                    "task": str(record.get("task_name", "unknown")),
                },
            }
        )
        if len(cases) > 10000:
            raise ValueError("Export exceeds 10000 cases")
    if not cases:
        raise ValueError("Empty export")
    return cases
