"""Tests for the feedback capture store + API (offline, no LLM/network)."""
import importlib


def _fresh(tmp_path, monkeypatch):
    """Reload feedback.py pointed at a throwaway file so tests don't touch real data."""
    monkeypatch.setenv("FEEDBACK_PATH", str(tmp_path / "fb.jsonl"))
    import feedback
    importlib.reload(feedback)
    return feedback


def test_record_and_list_roundtrip(tmp_path, monkeypatch):
    fb = _fresh(tmp_path, monkeypatch)
    assert fb.count() == 0
    fb.record({"prompt": "how much is the tax penalty?", "rating": "up",
               "comment": "spot on", "pipeline": {"trace_id": "TRC-1", "rag": {"status": "ok"}}})
    fb.record({"prompt": "who won the football?", "rating": "down", "comment": "wrong"})
    assert fb.count() == 2
    items = fb.all_feedback()
    assert items[0]["prompt"] == "who won the football?"   # newest first
    assert items[0]["rating"] == "down"
    assert items[1]["pipeline"]["rag"]["status"] == "ok"   # pipeline snapshot kept
    assert items[1]["id"] and items[1]["ts"]               # stamped


def test_persists_to_disk(tmp_path, monkeypatch):
    fb = _fresh(tmp_path, monkeypatch)
    fb.record({"comment": "saved to disk"})
    assert (tmp_path / "fb.jsonl").exists()


def test_api_submit_and_get(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    import app
    importlib.reload(app)
    client = app.app.test_client()

    r = client.post("/api/feedback", json={
        "prompt": "how do I register a business?", "rating": "up",
        "comment": "clear and correct", "pipeline": {"trace_id": "TRC-9"}})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    listed = client.get("/api/feedback").get_json()
    assert listed["count"] == 1
    assert listed["items"][0]["comment"] == "clear and correct"


def test_api_rejects_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    import app
    importlib.reload(app)
    r = app.app.test_client().post("/api/feedback", json={"prompt": "just a prompt"})
    assert r.status_code == 400
