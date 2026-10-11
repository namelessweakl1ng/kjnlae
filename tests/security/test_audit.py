import json
import logging

from kjnlae.api.audit import AuditFormatter


def test_audit_formatter_is_allowlisted_and_does_not_echo_input():
    record = logging.makeLogRecord(
        {
            "msg": "scan_decision",
            "levelname": "INFO",
            "decision": "BLOCK",
            "status": 200,
            "text": "private secret",
            "authorization": "private key",
            "method": "POST",
        }
    )
    encoded = AuditFormatter().format(record)
    result = json.loads(encoded)
    assert result["decision"] == "BLOCK" and result["event"] == "scan_decision"
    assert "private" not in encoded and "authorization" not in encoded
