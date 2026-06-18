"""4-dimension → canonical nlp_intent_schema_v2 mapping + validation."""
from dataclasses import dataclass

import intent_schema


@dataclass
class CR:
    label: str
    confidence: float
    reasoning: str = ""


def _cls(in_scope="in_scope", safety="safe", request_type="general_info", service="general",
         conf=0.9):
    return {
        "in_scope": CR(in_scope, conf),
        "safety": CR(safety, conf),
        "request_type": CR(request_type, conf),
        "service": CR(service, conf),
    }


def test_unsafe_maps_to_escl():
    intent, conf, basis = intent_schema.map_to_canonical_intent(_cls(safety="unsafe"))
    assert intent == "ESCL" and "safety" in basis


def test_out_of_scope_maps_to_clarif():
    intent, *_ = intent_schema.map_to_canonical_intent(_cls(in_scope="out_of_scope"))
    assert intent == "CLARIF"


def test_request_type_mappings():
    assert intent_schema.map_to_canonical_intent(_cls(request_type="office_location"))[0] == "NAV"
    assert intent_schema.map_to_canonical_intent(_cls(request_type="application_start"))[0] == "TRANS"
    assert intent_schema.map_to_canonical_intent(_cls(request_type="document_inquiry"))[0] == "INFO"


def test_scores_have_all_five_keys_and_argmax():
    payload = intent_schema.to_canonical_payload(
        user_text="x", language="en", classification=_cls(request_type="office_location", conf=0.8),
        classifier_kind="KeywordClassifier",
    )
    scores = payload["classification"]["scores"]
    assert set(scores) == {"INFO", "NAV", "TRANS", "CLARIF", "ESCL"}
    assert max(scores, key=scores.get) == "NAV"
    assert abs(sum(scores.values()) - 1.0) < 1e-6


def test_low_confidence_flag():
    p = intent_schema.to_canonical_payload(
        user_text="x", language="en", classification=_cls(request_type="other", conf=0.4),
        classifier_kind="KeywordClassifier")
    assert p["classification"]["low_confidence_flag"] is True


def test_validates_against_extended_but_diverges_from_strict_canonical():
    p = intent_schema.to_canonical_payload(
        user_text="hello", language="en", classification=_cls(),
        classifier_kind="KeywordClassifier", entities={"tax_year": "2026"},
        routing={"agent": "permit_agent"}, trace_id="TRC-ABCD1234")
    ok_ext, err_ext = intent_schema.validate(p)
    assert ok_ext is True, err_ext
    ok_strict, _ = intent_schema.validate(p, strict_canonical=True)
    # strict canonical rejects the additive `extensions` / non-NLLB model_id
    assert ok_strict is False


def test_request_id_is_uuid4_shaped():
    import re
    p = intent_schema.to_canonical_payload(
        user_text="x", language="en", classification=_cls(), classifier_kind="GeminiClassifier")
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
                    p["request_id"])
    assert p["metadata"]["model_id"] == "gemini-2.5-flash"
