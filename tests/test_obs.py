"""Structured logging + trace_id helpers (Team D schema)."""
import obs


def test_generate_and_validate_trace_id():
    tid = obs.generate_trace_id()
    assert tid.startswith("TRC-")
    assert obs.validate_trace_id(tid)
    assert obs.validate_trace_id("3f6a1b2c-84d5-4e7f-a1b0-9c2d3e4f5678")  # UUID also accepted
    assert not obs.validate_trace_id("")
    assert not obs.validate_trace_id("nope nope")


def test_log_event_has_team_d_schema_fields():
    entry = obs.log_event("INFO", "test.event", "hi", trace_id="TRC-AAAA1111", foo="bar")
    for field in ("timestamp", "level", "trace_id", "service", "event", "message", "metadata"):
        assert field in entry
    assert entry["trace_id"] == "TRC-AAAA1111"
    assert entry["metadata"]["foo"] == "bar"


def test_context_var_roundtrip():
    token = obs.set_trace_id("TRC-CTX00001")
    assert obs.get_trace_id() == "TRC-CTX00001"
    obs.reset_trace_id(token)
