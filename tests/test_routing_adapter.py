"""Routing adapter: UI-compatible shape, backend selection, agent gating."""
import routing_adapter


def test_route_returns_ui_shape():
    r = routing_adapter.route("I want to register a new business in Thimphu", trace_id="TRC-TEST0001")
    for key in ("agent", "intent", "confidence", "slots"):
        assert key in r.routing
    assert r.backend.startswith("rule")


def test_business_registration_intent():
    r = routing_adapter.route("I want to register a new business in Thimphu", trace_id="TRC-TEST0002")
    assert r.routing["intent"] == "business_registration"
    assert r.routing["agent"] == "business_reg_agent"


def test_agent_path_disabled_by_default(monkeypatch):
    # Without USE_TEAM_B_AGENT + GROQ_API_KEY the heavy LangGraph path must not run.
    monkeypatch.delenv("USE_TEAM_B_AGENT", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert routing_adapter._agent_enabled() is False
    r = routing_adapter.route("hello", trace_id="TRC-TEST0003")
    assert not r.backend.startswith("agent[")


def test_agent_requires_both_flag_and_key(monkeypatch):
    monkeypatch.setenv("USE_TEAM_B_AGENT", "1")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert routing_adapter._agent_enabled() is False  # flag alone is not enough
