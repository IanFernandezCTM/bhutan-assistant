"""
═══════════════════════════════════════════════════════════════════════
  transactions.py — sovereign, in-process government-record lookups.

  This is the prototype's answer to the one thing Team B's agent did that the
  grounded assistant did not: TRANSACTIONS — looking up a citizen's own
  business / tax / land / licence record by its ID.

  Design goals (see LOCAL_FIRST_PLAN.md §1, step 4 — "agentic ONLY here"):
    • SOVEREIGN — pure Python, no Groq, no LangGraph, no network, no extra LLM
      call. Deterministic ID extraction + an in-process lookup. Runs entirely on
      hardware the government owns.
    • PRECISE TRIGGER — a transaction fires ONLY when a concrete record
      identifier is present (a business/licence ID, or a thram+plot pair). Plain
      informational questions ("how do I register a business?") never trigger a
      lookup — they stay on the grounded-RAG path.
    • OWNERSHIP CHECK (one better than Team B) — a record that carries an owner
      identity (business owner CID, land CID) is only revealed in full when the
      requester's CID matches the record's owner. Otherwise we return
      needs_verification and reveal nothing sensitive. Team B returned records to
      anyone who knew the ID; a government service must not.

  Data source / credit:
    The mock registries below are vendored from Team B's tool layer
    (team_b/langgraph_agent/tools.py) so the feature works on the deploy repo,
    where the team_b/ package is not present — the same vendoring pattern used by
    rag.py and team_b_routing.py. When running inside the monorepo, the real
    Team B land-registry service is used if importable.

  Toggle:  ENABLE_TRANSACTIONS=1 (default on). Set to 0 to disable entirely.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

ENABLE_TRANSACTIONS = os.environ.get("ENABLE_TRANSACTIONS", "1").strip().lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────────────────────────────
# Vendored mock registries (Team B — team_b/langgraph_agent/tools.py).
# Keyed by the identifier a citizen would speak/type.
# ─────────────────────────────────────────────────────────────────────
_MOCK_BUSINESS: Dict[str, Dict] = {
    "BT-PERMIT-2026-1234": {
        "company_name": "Druk Logistics & Co.", "status": "APPROVED",
        "license_type": "Commercial Freight & Transport", "clearance_level": "Level 1",
        "location": "Thimphu, Bhutan", "owner_cid": "11503012345",
    },
    "BT-REG-2026-9988": {
        "company_name": "Paro Artisan Weaver Guild", "status": "PENDING_REVIEW",
        "license_type": "Cottage Industry Manufacturing", "clearance_level": "Level 0",
        "location": "Paro, Bhutan", "owner_cid": "10901012345",
    },
}

_MOCK_TAX: Dict[str, Dict] = {
    "BT-PERMIT-2026-1234": {
        "tax_id": "TPN-776152-A", "filing_status": "COMPLIANT",
        "outstanding_penalties": "0.0", "next_deadline": "2026-09-30",
    },
    "BT-REG-2026-9988": {
        "tax_id": "TPN-882191-B", "filing_status": "DELINQUENT",
        "outstanding_penalties": "4500.00", "next_deadline": "IMMEDIATE_ACTION_REQUIRED",
    },
}

_MOCK_LAND: Dict[Tuple[str, str], Dict] = {
    ("TH-441", "PLOT-90"): {
        "owner_name": "Karma Wangchuk", "cid": "11503012345", "gewog": "Punakha Gewog",
        "dzongkhag": "Punakha", "land_use_category": "Residential",
    },
    ("TH-882", "PLOT-12"): {
        "owner_name": "Sonam Choden", "cid": "10901012345", "gewog": "Sarpang",
        "dzongkhag": "Sarpang", "land_use_category": "Agricultural",
    },
}

# Licences are permit-application status (no personal owner CID) → treated as
# non-sensitive public status, revealed without an ownership check.
_MOCK_LICENCE: Dict[str, Dict] = {
    "BT-LIC-2026-0011": {
        "applicant": "Tashi Dema", "permit_type": "Rural Timber — New Construction",
        "status": "APPROVED", "timber_volume_m3": "12.5", "location": "Punakha Gewog",
        "issued_date": "2026-01-15",
    },
    "BT-LIC-2026-0042": {
        "applicant": "Pema Wangchuk", "permit_type": "Private Land Removal",
        "status": "PENDING_REVIEW", "timber_volume_m3": "8.0", "location": "Sarpang",
        "issued_date": "not yet issued",
    },
}

# Best-effort: use Team B's REAL land-registry service in the monorepo. Absent on
# the deploy repo → we fall back to the vendored records above. (Same pattern as
# rag.py / routing_adapter.py.)
try:  # pragma: no cover - environment dependent
    import sys
    from pathlib import Path
    _REPO_ROOT = str(Path(__file__).resolve().parents[1])
    if _REPO_ROOT not in sys.path:
        sys.path.append(_REPO_ROOT)
    from shared.mock_endpoints.land_registry_lookup_service import query_land_registry as _real_land_lookup  # type: ignore
    UPSTREAM_LAND_AVAILABLE = True
except Exception:
    _real_land_lookup = None
    UPSTREAM_LAND_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────
# Deterministic identifier extraction (mirrors Team B's regexes).
# ─────────────────────────────────────────────────────────────────────
_RE_BIZ = re.compile(r"BT-(?:PERMIT|REG)-\d{4}-\d+", re.IGNORECASE)
_RE_LIC = re.compile(r"BT-LIC-\d{4}-\d+", re.IGNORECASE)
_RE_THRAM = re.compile(r"\bTH[- ]?(\d+)\b", re.IGNORECASE)
_RE_PLOT = re.compile(r"\bPLOT[- ]?(\d+)\b", re.IGNORECASE)
_RE_CID = re.compile(r"\b(1\d{10})\b")

_TAX_CUES = ("tax", "penalt", "filing", "file ", "owe", "complian", "fine",
             "fee", "delinquent", "outstanding", "arrears")


def _find_biz(text: str) -> Optional[str]:
    m = _RE_BIZ.search(text)
    return m.group(0).upper() if m else None


def _find_licence(text: str) -> Optional[str]:
    m = _RE_LIC.search(text)
    return m.group(0).upper() if m else None


def _find_land(text: str) -> Optional[Tuple[str, str]]:
    th, pl = _RE_THRAM.search(text), _RE_PLOT.search(text)
    if th and pl:
        return (f"TH-{th.group(1)}", f"PLOT-{pl.group(1)}")
    return None


def _find_cid(text: str, entities: Optional[Dict] = None) -> Optional[str]:
    if entities and entities.get("citizenship_id"):
        return str(entities["citizenship_id"])
    m = _RE_CID.search(text)
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────
# Result assembly
# ─────────────────────────────────────────────────────────────────────
def _fmt(record: Dict, fields: List[Tuple[str, str]]) -> str:
    """Render selected (label, key) pairs as 'Label: value' lines."""
    return "\n".join(f"{label}: {record[key]}" for label, key in fields if key in record)


def _result(kind: str, identifier: str, status: str, *,
            record_text: str = "", source: str = "", hint: str = "") -> Dict:
    """Build the normalized transaction result the pipeline consumes.

    status ∈ {authorized, needs_verification, not_found}
      • authorized         — owner verified (or non-sensitive licence); reveal record_text
      • needs_verification — record exists but requester identity not proven; reveal NOTHING
      • not_found          — no such record
    """
    return {
        "is_transaction": True,
        "kind": kind,
        "id": identifier,
        "status": status,
        "authorized": status == "authorized",
        "record_text": record_text,
        "source": source,
        "hint": hint,
    }


def _land_record(land: Tuple[str, str]) -> Optional[Dict]:
    """Vendored record first; then Team B's real service if present."""
    if land in _MOCK_LAND:
        return _MOCK_LAND[land]
    if _real_land_lookup is not None:  # pragma: no cover - requires monorepo infra
        try:
            got = _real_land_lookup(thram_no=land[0], plot_no=land[1])
            if isinstance(got, dict):
                return got
        except Exception:
            return None
    return None


def detect_and_lookup(text: str, entities: Optional[Dict] = None) -> Optional[Dict]:
    """Return a transaction result, or None if this is not a record lookup.

    A transaction fires ONLY when a concrete identifier is present (business /
    licence ID, or thram+plot). This keeps informational questions on the
    grounded-RAG path untouched.
    """
    if not ENABLE_TRANSACTIONS or not text:
        return None

    cid = _find_cid(text, entities)
    biz = _find_biz(text)
    lic = _find_licence(text)
    land = _find_land(text)
    low = text.lower()

    # ── Business ID present → tax record (if tax-flavoured) else business record.
    if biz:
        is_tax = any(cue in low for cue in _TAX_CUES)
        registry = _MOCK_TAX if is_tax else _MOCK_BUSINESS
        kind = "tax" if is_tax else "business"
        source = "Bhutan Tax/RRCO registry (mock)" if is_tax else "Bhutan Business registry (mock)"
        if biz not in _MOCK_BUSINESS:  # ownership is defined by the business owner
            return _result(kind, biz, "not_found", source=source,
                           hint=f"No {kind} record matches business ID {biz}.")
        owner_cid = _MOCK_BUSINESS[biz]["owner_cid"]
        if cid != owner_cid:
            return _result(kind, biz, "needs_verification", source=source,
                           hint=(f"A {kind} record for {biz} exists but the requester's identity is "
                                 f"NOT verified. Reveal NO details; ask them to confirm their own CID "
                                 f"or visit the office in person."))
        rec = registry[biz]
        if is_tax:
            body = _fmt(rec, [("Tax ID", "tax_id"), ("Filing status", "filing_status"),
                              ("Outstanding penalties (Nu.)", "outstanding_penalties"),
                              ("Next deadline", "next_deadline")])
        else:
            body = _fmt(rec, [("Company", "company_name"), ("Status", "status"),
                              ("Licence type", "license_type"), ("Clearance level", "clearance_level"),
                              ("Location", "location")])
        return _result(kind, biz, "authorized", record_text=body, source=source,
                       hint=f"Identity verified (CID matches owner). This is the citizen's own {kind} record.")

    # ── Licence ID → permit-application status (non-sensitive, no ownership gate).
    if lic:
        if lic not in _MOCK_LICENCE:
            return _result("licensing", lic, "not_found", source="Licensing board (mock)",
                           hint=f"No licence record matches {lic}.")
        rec = _MOCK_LICENCE[lic]
        body = _fmt(rec, [("Applicant", "applicant"), ("Permit type", "permit_type"),
                          ("Status", "status"), ("Timber volume (m³)", "timber_volume_m3"),
                          ("Location", "location"), ("Issued date", "issued_date")])
        return _result("licensing", lic, "authorized", record_text=body,
                       source="Licensing board (mock)", hint="Permit-application status.")

    # ── Land (thram + plot) → land record, gated by owner CID.
    if land:
        identifier = f"{land[0]} {land[1]}"
        rec = _land_record(land)
        if rec is None:
            return _result("land", identifier, "not_found", source="National Land Commission (mock)",
                           hint=f"No land record matches {identifier}.")
        owner_cid = str(rec.get("cid", ""))
        if cid != owner_cid:
            return _result("land", identifier, "needs_verification",
                           source="National Land Commission (mock)",
                           hint=(f"A land record for {identifier} exists but the requester's identity is "
                                 f"NOT verified. Reveal NO owner details; ask them to confirm their own "
                                 f"CID or visit the Land Commission."))
        rec = {**rec, "_thram": land[0], "_plot": land[1]}
        body = _fmt(rec, [("Thram no.", "_thram"), ("Plot no.", "_plot"),
                          ("Owner", "owner_name"), ("Owner CID", "cid"), ("Gewog", "gewog"),
                          ("Dzongkhag", "dzongkhag"), ("Land use", "land_use_category")])
        return _result("land", identifier, "authorized", record_text=body,
                       source="National Land Commission (mock)",
                       hint="Identity verified (CID matches owner). This is the citizen's own land record.")

    return None


# ─────────────────────────────────────────────────────────────────────
# Rendering for the LLM-first path (context block) and the offline path (text).
# ─────────────────────────────────────────────────────────────────────
def context_block(result: Dict) -> str:
    """The authoritative block injected into the single grounded LLM call."""
    kind = result["kind"]
    if result["status"] == "authorized":
        return (f"LIVE RECORD — {kind.upper()} lookup for {result['id']} "
                f"[IDENTITY VERIFIED — you may share these exact values]:\n{result['record_text']}")
    if result["status"] == "needs_verification":
        return (f"LIVE RECORD — {kind.upper()} lookup for {result['id']} "
                f"[IDENTITY NOT VERIFIED — DO NOT reveal any record details]:\n{result['hint']}")
    return f"LIVE RECORD — {kind.upper()} lookup for {result['id']} [NOT FOUND]:\n{result['hint']}"


def render_text(result: Dict) -> str:
    """Ready-to-speak plain answer for the offline / no-LLM fallback path."""
    kind = result["kind"].replace("licensing", "licence")
    if result["status"] == "authorized":
        return (f"Here is the {kind} record for {result['id']}:\n{result['record_text']}\n\n"
                f"Is there anything else I can help you with?")
    if result["status"] == "needs_verification":
        return (f"I found a {kind} record for {result['id']}, but for privacy I can only share it "
                f"with the record's owner. Please confirm your own Citizenship ID (CID), or visit the "
                f"relevant office with your CID, and I can help further.")
    return (f"I couldn't find a {kind} record for {result['id']}. Please double-check the reference "
            f"number, or contact the relevant office for help.")
