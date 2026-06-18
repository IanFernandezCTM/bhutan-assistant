"""KeywordClassifier behaviour + GeminiClassifier short-circuit paths."""
from app import GeminiClassifier, KeywordClassifier


def test_keyword_returns_four_dimensions():
    out = KeywordClassifier().classify("How do I apply for a timber permit?")
    assert set(out) == {"in_scope", "safety", "request_type", "service"}
    for v in out.values():
        assert isinstance(v.label, str) and 0.0 <= v.confidence <= 1.0


def test_keyword_out_of_scope_word():
    out = KeywordClassifier().classify("Who won the cricket match yesterday?")
    assert out["in_scope"].label == "out_of_scope"


def test_keyword_unsafe_word():
    out = KeywordClassifier().classify("My stomach hurts, do I have cancer?")
    assert out["safety"].label == "unsafe"


def test_keyword_service_and_type():
    out = KeywordClassifier().classify("What documents do I need for a construction permit?")
    assert out["service"].label == "permits"
    assert out["request_type"].label == "document_inquiry"


def test_short_circuit_out_of_scope_skips_three():
    from app import ClassificationResult
    res = GeminiClassifier._short_circuit_out_of_scope(ClassificationResult("out_of_scope", 0.9))
    assert res["in_scope"].label == "out_of_scope"
    assert res["safety"].label == "safe"
    assert res["request_type"].label == "other"
    assert res["service"].label == "general"
    # the three skipped dims are explicitly marked
    for k in ("safety", "request_type", "service"):
        assert "short-circuited" in res[k].reasoning


def test_short_circuit_unsafe_skips_two():
    from app import ClassificationResult
    res = GeminiClassifier._short_circuit_unsafe(
        ClassificationResult("in_scope", 0.9), ClassificationResult("unsafe", 0.95)
    )
    assert res["safety"].label == "unsafe"
    assert res["request_type"].label == "other"
    assert res["service"].label == "general"
    for k in ("request_type", "service"):
        assert "short-circuited" in res[k].reasoning
