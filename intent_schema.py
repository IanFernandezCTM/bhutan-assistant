"""
═══════════════════════════════════════════════════════════════════════
  CANONICAL INTENT SCHEMA RECONCILIATION  (Phase 3 integration)

  The prototype's native classifier emits FOUR dimensions
  (in_scope / safety / request_type / service). Team D's canonical contract
  (test_nlp_intent_schema/nlp_intent_schema_v2.json) instead expects a single
  intent ∈ {INFO, NAV, TRANS, CLARIF, ESCL} with a 5-way score distribution.

  This module RECONCILES the two (maps, does not duplicate): it keeps the
  4-dimension output as the internal source of truth and emits a
  canonical-v2-conformant payload, validated against a vendored
  prototype-extended copy of the schema (schemas/nlp_intent_schema_v2.prototype.json).

  Why the extended copy: canonical v2 closes `model_id` to NLLB/XLM-R, so a
  Gemini/keyword payload fails strict validation, and `additionalProperties:false`
  forbids carrying the prototype's entities/routing. We therefore validate against
  an additive extension (PROTOTYPE model_family + an `extensions` block) and
  recommend an upstream enum-widening PR (see CROSS_TEAM_NOTES.md). We never edit
  Team D's canonical file in place.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
_EXTENDED_SCHEMA_PATH = SCHEMA_DIR / "nlp_intent_schema_v2.prototype.json"
_CANONICAL_SCHEMA_PATH = SCHEMA_DIR / "nlp_intent_schema_v2.json"

LOW_CONFIDENCE_THRESHOLD = 0.60  # canonical v2 definition

# request_type → canonical intent. (in_scope/out_of_scope and safety override below.)
_REQUEST_TYPE_TO_INTENT = {
    "office_location": "NAV",
    "facility_lookup": "NAV",
    "application_start": "TRANS",
    "status_check": "TRANS",
    "document_inquiry": "INFO",
    "eligibility_check": "INFO",
    "general_info": "INFO",
    "other": "INFO",
}

_MODEL_BY_CLASSIFIER = {
    "GeminiClassifier": ("PROTOTYPE", "gemini-2.5-flash"),
    "KeywordClassifier": ("PROTOTYPE", "keyword-baseline"),
}


def map_to_canonical_intent(classification: Dict) -> Tuple[str, float, str]:
    """Collapse the 4 dimensions into (canonical_intent, confidence, basis).

    Precedence: unsafe → ESCL; out_of_scope → CLARIF; else request_type mapping.
    `confidence` is taken from the dimension that drove the decision.
    """
    safety = classification.get("safety")
    in_scope = classification.get("in_scope")
    request_type = classification.get("request_type")

    if safety is not None and safety.label == "unsafe":
        return "ESCL", float(safety.confidence), "safety=unsafe"
    if in_scope is not None and in_scope.label == "out_of_scope":
        return "CLARIF", float(in_scope.confidence), "in_scope=out_of_scope"
    rt_label = request_type.label if request_type is not None else "general_info"
    rt_conf = float(request_type.confidence) if request_type is not None else 0.0
    intent = _REQUEST_TYPE_TO_INTENT.get(rt_label, "INFO")
    return intent, rt_conf, f"request_type={rt_label}"


def _build_scores(intent: str, confidence: float) -> Dict[str, float]:
    """Synthesize a 5-way distribution from a single confidence.

    NOTE: this is a documented SHIM — the prototype's classifier does not
    produce a real softmax. The argmax intent gets `confidence`; the remainder
    is split evenly across the other four classes.
    """
    labels = ["INFO", "NAV", "TRANS", "CLARIF", "ESCL"]
    confidence = max(0.0, min(1.0, float(confidence)))
    remainder = (1.0 - confidence) / 4.0
    scores = {lbl: round(remainder, 4) for lbl in labels}
    scores[intent] = round(confidence, 4)
    return scores


def _lang_code(language: str) -> str:
    return "dz" if language == "dz" else "en"


def to_canonical_payload(
    *,
    user_text: str,
    language: str,
    classification: Dict,
    classifier_kind: str,
    entities: Optional[Dict] = None,
    routing: Optional[Dict] = None,
    trace_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    translation: Optional[Dict] = None,
    request_id: Optional[str] = None,
) -> Dict:
    """Build a canonical-v2 (prototype-extended) intent payload."""
    intent, confidence, basis = map_to_canonical_intent(classification)
    model_family, model_id = _MODEL_BY_CLASSIFIER.get(classifier_kind, ("PROTOTYPE", "keyword-baseline"))

    payload = {
        "request_id": request_id or str(uuid.uuid4()),
        "input": {
            "text": user_text[:512],
            "language": _lang_code(language),
        },
        "classification": {
            "intent": intent,
            "confidence": round(float(confidence), 4),
            "scores": _build_scores(intent, confidence),
            "low_confidence_flag": bool(confidence < LOW_CONFIDENCE_THRESHOLD),
        },
        "translation": translation,
        "metadata": {
            "model_family": model_family,
            "model_id": model_id,
            "schema_version": "2.0.0",
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "inference_device": "cpu",
            "latency_ms": latency_ms,
        },
        "extensions": {
            "dimensions": {
                k: {"label": v.label, "confidence": round(float(v.confidence), 4)}
                for k, v in classification.items()
            },
            "entities": entities or {},
            "routing": routing or {},
            "mapping_basis": basis,
            "trace_id": trace_id or "",
        },
    }
    return payload


# ─────────────────────────────────────────────────────────────────────
# Validation (lazy jsonschema import so the app boots even without it)
# ─────────────────────────────────────────────────────────────────────
_extended_schema = None
_canonical_schema = None


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(payload: Dict, strict_canonical: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate against the prototype-extended schema (default) or strict canonical v2.

    Returns (ok, error_message). If jsonschema isn't installed, returns
    (True, "jsonschema-not-installed") so validation never blocks the request.
    """
    global _extended_schema, _canonical_schema
    try:
        import jsonschema
    except Exception:
        return True, "jsonschema-not-installed (skipped)"

    path = _CANONICAL_SCHEMA_PATH if strict_canonical else _EXTENDED_SCHEMA_PATH
    try:
        if strict_canonical:
            if _canonical_schema is None:
                _canonical_schema = _load(path)
            schema = _canonical_schema
        else:
            if _extended_schema is None:
                _extended_schema = _load(path)
            schema = _extended_schema
        jsonschema.validate(instance=payload, schema=schema)
        return True, None
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        return False, f"{exc.message} (at {'/'.join(str(p) for p in exc.absolute_path)})"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


if __name__ == "__main__":
    from dataclasses import dataclass

    @dataclass
    class CR:
        label: str
        confidence: float
        reasoning: str = ""

    samples = [
        {"in_scope": CR("in_scope", 0.9), "safety": CR("safe", 0.95),
         "request_type": CR("document_inquiry", 0.8), "service": CR("permits", 0.9)},
        {"in_scope": CR("in_scope", 0.9), "safety": CR("unsafe", 0.97),
         "request_type": CR("other", 1.0), "service": CR("general", 1.0)},
        {"in_scope": CR("out_of_scope", 0.85), "safety": CR("safe", 1.0),
         "request_type": CR("other", 1.0), "service": CR("general", 1.0)},
    ]
    for c in samples:
        p = to_canonical_payload(user_text="test query", language="en", classification=c,
                                 classifier_kind="KeywordClassifier", entities={"tax_year": "2026"},
                                 routing={"agent": "permit_agent"}, trace_id="TRC-TEST1234")
        ok_ext, err_ext = validate(p)
        ok_strict, err_strict = validate(p, strict_canonical=True)
        print(f"intent={p['classification']['intent']:6s} conf={p['classification']['confidence']:.2f} "
              f"low={p['classification']['low_confidence_flag']} | extended={ok_ext} "
              f"strict_canonical={ok_strict} ({err_strict})")
