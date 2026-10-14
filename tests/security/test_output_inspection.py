import pytest

from kjnlae.guards.output import OutputGuard


def test_output_exact_secrets_links_and_schema():
    guard = OutputGuard(
        secrets=("mock-secret-123",),
        allowed_hosts=frozenset({"example.test"}),
        allowed_fields=frozenset({"summary"}),
    )
    assert guard.inspect("mock-secret-123").decision == "BLOCK"
    assert guard.inspect("[click](https://evil.test)").decision == "BLOCK"
    assert guard.inspect("https://example.test.evil.test").decision == "BLOCK"
    assert guard.inspect("ok", {"command": "run"}).decision == "BLOCK"
    assert guard.inspect("https://example.test/path", {"summary": "ok"}).decision == "ALLOW"


def test_output_protocol_relative_and_unsupported_links():
    guard = OutputGuard(allowed_hosts=frozenset({"example.test"}))
    assert guard.inspect("[click](//evil.test/path)").decision == "BLOCK"
    assert guard.inspect('<a href="file:///etc/passwd">open</a>').decision == "BLOCK"
    assert guard.inspect('<a href="https://example.test">safe</a>').decision == "ALLOW"


def test_sdk_output_total_budget_matches_api():
    with pytest.raises(ValueError):
        OutputGuard().inspect("x" * 20000, {"summary": "x" * 20000})
