"""End-to-end: text & voice → classify → enrich → RAG → route → response,
asserting trace_id propagation across header, body and the pipeline report."""
import pytest


@pytest.fixture(scope="module")
def client():
    from app import app  # imported after conftest sets RAG_BACKEND=docs
    app.config.update(TESTING=True)
    return app.test_client()


def test_chat_full_pipeline_and_trace_id(client):
    resp = client.post("/api/chat", json={"message": "How much is the late filing penalty for income tax?"})
    assert resp.status_code == 200
    data = resp.get_json()

    # trace_id minted, echoed on the response header, and matches the body
    header_tid = resp.headers.get("X-Trace-ID")
    assert header_tid and header_tid.startswith("TRC-")
    assert data["trace_id"] == header_tid

    # every pipeline stage ran and is reported
    p = data["pipeline"]
    for stage in ("classify", "enrich", "rag", "route", "schema", "logging"):
        assert stage in p
    assert p["trace_id"] == header_tid

    # real components engaged: RAG over docs, Team B rule router, canonical schema
    assert p["rag"]["status"].startswith("real")          # RAG_BACKEND=docs
    assert p["route"]["component"].startswith("rule")
    assert p["schema"]["emitted"] is True
    assert p["schema"]["canonical_intent"] in {"INFO", "NAV", "TRANS", "CLARIF", "ESCL"}

    # the classic response contract is preserved (UI back-compat)
    for key in ("bot_text", "sources", "classification", "language", "entities", "routing", "classifier_kind"):
        assert key in data
    assert set(data["classification"]) == {"in_scope", "safety", "request_type", "service"}


def test_inbound_trace_id_is_honoured(client):
    resp = client.post("/api/chat", json={"message": "Where is the tax office?"},
                       headers={"X-Trace-ID": "TRC-DEADBEEF"})
    assert resp.get_json()["trace_id"] == "TRC-DEADBEEF"
    assert resp.headers.get("X-Trace-ID") == "TRC-DEADBEEF"


def test_voice_drives_same_pipeline(client):
    resp = client.post("/api/voice", json={"fixture_id": "en_business_thimphu"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["asr"]["source"] == "fixture"
    assert data["pipeline"]["asr"]["status"].startswith("stub")
    assert data["trace_id"] == resp.headers.get("X-Trace-ID")
    # same downstream stages as text
    for stage in ("classify", "enrich", "rag", "route", "schema"):
        assert stage in data["pipeline"]


def test_voice_client_transcript_unsafe_escalates(client):
    resp = client.post("/api/voice", json={
        "transcript": "My stomach hurts, do I have cancer?", "confidence": 0.88, "language": "en"})
    data = resp.get_json()
    assert data["classification"]["safety"]["label"] == "unsafe"
    assert data["canonical_intent"]["classification"]["intent"] == "ESCL"


def test_voice_bad_request(client):
    resp = client.post("/api/voice", json={})
    assert resp.status_code == 400
    assert "fixtures" in resp.get_json()


def test_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 400
