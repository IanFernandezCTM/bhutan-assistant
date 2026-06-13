"""
═══════════════════════════════════════════════════════════════════════
  SERVICE ROUTING LAYER
  Maps a request to the downstream government agent + routing slots.

  Source / credit:
    Adapted from Team B's routing module (team_b/routing_module/) — the
    deterministic IntentRouter, its four route handlers, and the slot
    helpers. Same intents, agents, keywords, and slot regexes; the only
    change is making it self-contained (no team_b package imports and no
    internal logging) so it deploys at the prototype's repo root.

  Why this exists:
    Your Gemini classifier says WHAT a request is about, and Team A's
    enrichment says WHAT LANGUAGE + DETAILS it carries. Team B's router
    answers the next question: WHERE does it go — which downstream agent
    (permit_agent, business_reg_agent, health_info_agent, …) should
    handle it, and what routing slots (district, facility, document,
    agency) were pulled out. That's the hand-off layer of the system.

  Dependency-free (regex only): adds nothing to requirements.txt.
═══════════════════════════════════════════════════════════════════════
"""

import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional


# ── Shared routing data structure (Team B's schema.IntentRoute) ─────────
@dataclass(frozen=True)
class IntentRoute:
    intent: str
    agent: str
    confidence: float
    slots: Dict[str, str]
    matched_keywords: List[str]
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# ── Shared helpers (Team B's routing_module/utils.py) ───────────────────
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def match_keywords(text: str, keywords: Iterable[str]) -> List[str]:
    return [kw for kw in keywords if kw in text]


def extract_slots(text: str, patterns: Dict[str, "re.Pattern[str]"],
                  slot_names: Iterable[str]) -> Dict[str, str]:
    slots: Dict[str, str] = {}
    for slot_name in slot_names:
        pattern = patterns.get(slot_name)
        if not pattern:
            continue
        match = pattern.search(text)
        if match:
            slots[slot_name] = match.group(1 if match.lastindex else 0).strip()
    return slots


def score_confidence(match_count: int, keyword_pool_size: int) -> float:
    if keyword_pool_size <= 0:
        return 0.0
    confidence = 0.45 + (match_count / keyword_pool_size) * 0.45
    return round(min(confidence, 0.95), 2)


_DISTRICTS = (
    r"\b(thimphu|paro|punakha|wangdue|bumthang|trongsa|tsirang|samtse|"
    r"phuentsholing|gasa|haa|mongar|trashigang|pemagatshel|samdrup|"
    r"zhemgang|dagana|lhuntse|tashiyangtse)\b"
)


# ── Route handlers (team_b/routing_module/routes/*) ─────────────────────
def _route_business_registration(text: str) -> Optional[IntentRoute]:
    t = normalize_text(text)
    if not t:
        return None
    matches_rule = (
        ("business" in t and ("register" in t or "registration" in t))
        or "trade license" in t
        or "company setup" in t
        or "sole proprietorship" in t
        or "new business" in t
    )
    if not matches_rule:
        return None
    matched = match_keywords(t, (
        "business registration", "new business", "trade license",
        "company setup", "business license", "startup", "sole proprietorship",
    ))
    slots = extract_slots(t, {"district": re.compile(_DISTRICTS, re.IGNORECASE)}, ("district",))
    return IntentRoute(
        intent="business_registration", agent="business_reg_agent",
        confidence=0.82, slots=slots, matched_keywords=matched,
        reason="Matched business-registration rules",
    )


def _route_permit_support(text: str) -> Optional[IntentRoute]:
    t = normalize_text(text)
    if not t:
        return None
    keywords = ("permit", "license", "application form",
                "document checklist", "renewal", "approval")
    matched = match_keywords(t, keywords)
    if not matched:
        return None
    slot_patterns = {
        "document_type": re.compile(
            r"\b(id card|cid|passport|tax form|permit form|application form|"
            r"business license|trade license)\b", re.IGNORECASE),
        "agency": re.compile(
            r"\b(moic|mohca|moha|municipality|thromde|licensing board)\b",
            re.IGNORECASE),
    }
    slots = extract_slots(t, slot_patterns, ("document_type", "agency"))
    return IntentRoute(
        intent="permit_support", agent="permit_agent",
        confidence=score_confidence(len(matched), len(keywords)),
        slots=slots, matched_keywords=matched,
        reason=f"Matched {len(matched)} keyword(s)",
    )


def _route_health_service_info(text: str) -> Optional[IntentRoute]:
    t = normalize_text(text)
    if not t:
        return None
    keywords = ("hospital", "clinic", "health", "medicine",
                "doctor", "appointment", "emergency", "ambulance")
    matched = match_keywords(t, keywords)
    if not matched:
        return None
    slot_patterns = {
        "facility": re.compile(
            r"\b(hospital|clinic|bhutan medical|bhutanese hospital)\b",
            re.IGNORECASE),
        "district": re.compile(_DISTRICTS, re.IGNORECASE),
    }
    slots = extract_slots(t, slot_patterns, ("facility", "district"))
    return IntentRoute(
        intent="health_service_info", agent="health_info_agent",
        confidence=score_confidence(len(matched), len(keywords)),
        slots=slots, matched_keywords=matched,
        reason=f"Matched {len(matched)} keyword(s)",
    )


def _route_general_inquiry(text: str) -> Optional[IntentRoute]:
    t = normalize_text(text)
    if not t:
        return None
    keywords = ("how do i", "help", "information", "process", "requirements")
    matched = match_keywords(t, keywords)
    if not matched:
        return None
    slot_patterns = {
        "topic": re.compile(r"\b(tax|business|permit|health|license|registration)\b",
                            re.IGNORECASE),
    }
    slots = extract_slots(t, slot_patterns, ("topic",))
    return IntentRoute(
        intent="general_inquiry", agent="general_fallback_agent",
        confidence=score_confidence(len(matched), len(keywords)),
        slots=slots, matched_keywords=matched,
        reason=f"Matched {len(matched)} keyword(s)",
    )


# Handler order matters — same priority as Team B's IntentRouter.
_ROUTE_HANDLERS = (
    _route_business_registration,
    _route_permit_support,
    _route_health_service_info,
    _route_general_inquiry,
)


def _fallback_topic(text: str) -> str:
    for topic in ("tax", "business", "permit", "health", "license", "registration"):
        if topic in text:
            return topic
    return "general"


def route_intent(text: str) -> Dict[str, object]:
    """Public entry point used by app.py. Returns Team B's IntentRoute as a dict."""
    normalized = normalize_text(text)
    if not normalized:
        return IntentRoute("fallback", "general_fallback_agent", 0.0, {}, [],
                           "Empty input").to_dict()

    for handler in _ROUTE_HANDLERS:
        result = handler(text)
        if result is not None:
            return result.to_dict()

    return IntentRoute(
        intent="fallback", agent="general_fallback_agent", confidence=0.2,
        slots={"topic": _fallback_topic(normalized)}, matched_keywords=[],
        reason="No intent keywords matched",
    ).to_dict()


if __name__ == "__main__":
    samples = [
        "I want to register a new business in Thimphu.",
        "What documents do I need for a permit renewal?",
        "Which clinic in Paro can I visit for a doctor appointment?",
        "I need help with something else.",
    ]
    for s in samples:
        print(f"{s!r:60} -> {route_intent(s)}")
