"""JSON audit events with an explicit privacy allowlist."""

import json
import logging


class AuditFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = str(record.msg)
        if event not in {"http_result", "scan_decision", "action_decision", "output_decision"}:
            event = "security_event"
        fields = {
            name: getattr(record, name)
            for name in ("method", "status", "decision", "degraded", "inspection_complete")
            if hasattr(record, name)
        }
        return json.dumps({"at": record.created, "event": event, **fields}, separators=(",", ":"))


def configure_audit() -> logging.Logger:
    logger = logging.getLogger("kjnlae.audit")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(AuditFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
