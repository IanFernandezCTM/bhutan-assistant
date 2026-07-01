"""Tests for the LLM-first grounded assistant + grounding retrieval.

All offline: the LLM call is monkeypatched, so no API key or network is needed.
"""
import json

import assistant
import llm
import rag


def test_retrieve_grounding_pairs_en_and_dz():
    bundle = rag.retrieve_grounding("late filing penalty income tax", top_k=3)
    assert bundle, "should retrieve at least one tax section"
    assert all("en_text" in b and b["en_text"] for b in bundle)
    # The tax policy has a parallel Dzongkha file → at least one hit should be paired.
    assert any(b.get("dz_text") for b in bundle), "expected an aligned native Dzongkha passage"


def test_assistant_parses_structured_answer(monkeypatch):
    canned = json.dumps({
        "in_scope": True, "safe": True, "service": "taxes",
        "answer": "The late filing penalty is Nu. 100 per day of delay.",
        "sources_used": ["tax_policy.txt"], "confidence": 0.92, "abstained": False,
    })
    monkeypatch.setattr(llm, "chat", lambda *a, **k: canned)
    out = assistant.answer(
        "late penalty?", "en",
        [{"source": "tax_policy.txt", "title": "3. FILING", "en_text": "Nu. 100 per day", "dz_text": ""}],
    )
    assert out["service"] == "taxes"
    assert "100" in out["answer"]
    assert out["in_scope"] is True and out["safe"] is True
    assert out["abstained"] is False


def test_assistant_abstains_when_flagged(monkeypatch):
    canned = json.dumps({
        "in_scope": True, "safe": True, "service": "general",
        "answer": "I don't have that official information; please contact the office.",
        "sources_used": [], "confidence": 0.1, "abstained": True,
    })
    monkeypatch.setattr(llm, "chat", lambda *a, **k: canned)
    out = assistant.answer("who won the football?", "en", [])
    assert out["abstained"] is True


def test_assistant_handles_non_json_prose(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Just some prose, not JSON at all.")
    out = assistant.answer("hello", "en", [])
    assert out["answer"]
    assert out.get("parse_error") is True


def test_assistant_injects_transaction_block(monkeypatch):
    """The LIVE RECORD block must reach the single grounded call's user message."""
    captured = {}

    def fake_chat(messages, *a, **k):
        captured["user"] = messages[-1]["content"]
        return json.dumps({
            "in_scope": True, "safe": True, "service": "business",
            "answer": "Your business BT-PERMIT-2026-1234 is APPROVED.",
            "sources_used": [], "confidence": 0.95, "abstained": False,
        })

    monkeypatch.setattr(llm, "chat", fake_chat)
    block = ("LIVE RECORD — BUSINESS lookup for BT-PERMIT-2026-1234 "
             "[IDENTITY VERIFIED — you may share these exact values]:\nStatus: APPROVED")
    out = assistant.answer("is my business approved?", "en", [], transaction=block)
    assert "LIVE RECORD" in captured["user"]
    assert "APPROVED" in out["answer"]
    assert out["abstained"] is False


def test_assistant_strips_markdown_fence(monkeypatch):
    fenced = "```json\n" + json.dumps({
        "in_scope": True, "safe": True, "service": "permits",
        "answer": "You need your CID and Land Thram.",
        "sources_used": ["land_policy.txt"], "confidence": 0.8, "abstained": False,
    }) + "\n```"
    monkeypatch.setattr(llm, "chat", lambda *a, **k: fenced)
    out = assistant.answer("permit docs?", "en", [])
    assert out["service"] == "permits"
    assert "CID" in out["answer"]
