"""Tests for the sovereign, in-process transactional lookups (transactions.py).

All offline and deterministic — no LLM, no network, no external service.
Covers: precise triggering, the ownership check (authorized vs needs_verification),
not-found, tax-vs-business disambiguation, land, licence, and the render/context text.
"""
import transactions as tx


# ── Triggering: only a concrete ID starts a transaction ────────────────
def test_no_trigger_on_informational_question():
    assert tx.detect_and_lookup("How do I register a new business in Thimphu?") is None


def test_no_trigger_on_plain_greeting():
    assert tx.detect_and_lookup("kuzuzangpo, can you help me?") is None


# ── Business lookup + ownership check ──────────────────────────────────
def test_business_authorized_when_cid_matches_owner():
    r = tx.detect_and_lookup("What is the status of BT-PERMIT-2026-1234? My CID is 11503012345")
    assert r["kind"] == "business" and r["status"] == "authorized" and r["authorized"] is True
    assert "Druk Logistics" in r["record_text"]
    assert "APPROVED" in r["record_text"]


def test_business_needs_verification_without_cid():
    r = tx.detect_and_lookup("What is the status of BT-PERMIT-2026-1234?")
    assert r["status"] == "needs_verification" and r["authorized"] is False
    # No sensitive details leak into the injected block.
    assert "Druk Logistics" not in tx.context_block(r)


def test_business_needs_verification_with_wrong_cid():
    r = tx.detect_and_lookup("Status of BT-PERMIT-2026-1234, CID 10901012345")
    assert r["status"] == "needs_verification"


def test_business_not_found():
    r = tx.detect_and_lookup("Check business BT-REG-2099-0000, my CID 11503012345")
    assert r["status"] == "not_found"


# ── Tax vs business disambiguation on the same ID ──────────────────────
def test_tax_flavoured_query_hits_tax_registry():
    r = tx.detect_and_lookup("Any outstanding tax penalties for BT-REG-2026-9988? CID 10901012345")
    assert r["kind"] == "tax" and r["status"] == "authorized"
    assert "DELINQUENT" in r["record_text"]
    assert "4500.00" in r["record_text"]   # amount preserved verbatim


# ── Land lookup + ownership check ──────────────────────────────────────
def test_land_authorized_when_cid_matches():
    r = tx.detect_and_lookup("Who owns land TH-441 PLOT-90? My CID is 11503012345")
    assert r["kind"] == "land" and r["status"] == "authorized"
    assert "Karma Wangchuk" in r["record_text"]


def test_land_needs_verification_without_cid():
    r = tx.detect_and_lookup("Look up land TH-441 PLOT-90")
    assert r["status"] == "needs_verification"
    assert "Karma Wangchuk" not in tx.context_block(r)


def test_land_not_found():
    r = tx.detect_and_lookup("Land TH-999 PLOT-1, CID 11503012345")
    assert r["status"] == "not_found"


# ── Licence: public permit status, no ownership gate ───────────────────
def test_licence_authorized_without_cid():
    r = tx.detect_and_lookup("Status of licence BT-LIC-2026-0011")
    assert r["kind"] == "licensing" and r["status"] == "authorized"
    assert "APPROVED" in r["record_text"]


# ── Rendering ──────────────────────────────────────────────────────────
def test_render_text_authorized_contains_record():
    r = tx.detect_and_lookup("Status of BT-PERMIT-2026-1234, CID 11503012345")
    text = tx.render_text(r)
    assert "Druk Logistics" in text


def test_render_text_needs_verification_hides_record():
    r = tx.detect_and_lookup("Status of BT-PERMIT-2026-1234")
    text = tx.render_text(r)
    assert "Druk Logistics" not in text
    assert "CID" in text  # asks the citizen to verify


def test_context_block_tags_verified():
    r = tx.detect_and_lookup("Status of BT-PERMIT-2026-1234, CID 11503012345")
    assert "IDENTITY VERIFIED" in tx.context_block(r)


# ── Toggle ─────────────────────────────────────────────────────────────
def test_disabled_via_flag(monkeypatch):
    monkeypatch.setattr(tx, "ENABLE_TRANSACTIONS", False)
    assert tx.detect_and_lookup("Status of BT-PERMIT-2026-1234, CID 11503012345") is None
