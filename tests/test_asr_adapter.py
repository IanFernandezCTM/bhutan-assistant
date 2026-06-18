"""Team C voice-input adapter."""
import pytest

import asr_adapter


def test_client_transcript():
    r = asr_adapter.transcribe(transcript="How do I register my child's birth?", confidence=0.9)
    assert r.source == "client"
    assert r.language == "en"
    assert r.confidence == 0.9


def test_client_transcript_detects_dzongkha():
    r = asr_adapter.transcribe(transcript="ཁྲལ་སྤྲོད་ 2026")
    assert r.language == "dz"
    assert r.confidence == 1.0  # default when client omits confidence


def test_fixture_lookup():
    r = asr_adapter.transcribe(fixture_id="dz_tax_2026")
    assert r.source == "fixture"
    assert r.language == "dz"
    assert 0.0 <= r.confidence <= 1.0


def test_unknown_fixture_raises():
    with pytest.raises(ValueError):
        asr_adapter.transcribe(fixture_id="does_not_exist")


def test_empty_input_raises():
    with pytest.raises(ValueError):
        asr_adapter.transcribe()


def test_confidence_clamped():
    r = asr_adapter.transcribe(transcript="hi", confidence=5.0)
    assert r.confidence == 1.0
