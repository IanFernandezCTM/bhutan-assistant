"""
═══════════════════════════════════════════════════════════════════════
  VOICE INPUT ADAPTER  (Phase 3 integration — Team C)

  Accepts a transcription (text + confidence + language tag) so voice input
  can drive the SAME pipeline as typed chat. This is the realistic Team C
  contract: Team C's ASR (Whisper + Silero VAD; team_c_voice/) produces text,
  the prototype consumes it.

  Why an adapter and not a direct import: team_c_voice/ ships standalone scripts
  that load models and start interactive record/REPL loops AT IMPORT, expose no
  function returning {transcript, confidence, language}, and never compute a
  confidence score. They are not importable as a library. So this adapter:
    • accepts a client-supplied transcription (the live integration point), or
    • serves a canned fixture from asr_fixtures.json (offline demo/testing),
  and is honest that real in-process ASR is NOT wired (see CROSS_TEAM_NOTES.md).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from nlp_enrichment import detect_language

_FIXTURES_PATH = Path(__file__).resolve().parent / "asr_fixtures.json"

# Team C's pipeline is script-only and not importable; record that honestly.
REAL_ASR_AVAILABLE = False


@dataclass
class AsrResult:
    transcript: str
    confidence: float
    language: str
    source: str          # "client" | "fixture"
    detail: str = ""

    def to_dict(self) -> Dict:
        return {
            "transcript": self.transcript,
            "confidence": self.confidence,
            "language": self.language,
            "source": self.source,
            "detail": self.detail,
            "real_asr_available": REAL_ASR_AVAILABLE,
        }


_fixtures_cache: Optional[Dict[str, Dict]] = None


def _load_fixtures() -> Dict[str, Dict]:
    global _fixtures_cache
    if _fixtures_cache is None:
        data = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
        _fixtures_cache = {f["id"]: f for f in data.get("fixtures", [])}
    return _fixtures_cache


def list_fixtures() -> list:
    return list(_load_fixtures().keys())


def transcribe(
    transcript: Optional[str] = None,
    confidence: Optional[float] = None,
    language: Optional[str] = None,
    fixture_id: Optional[str] = None,
) -> AsrResult:
    """Resolve a voice turn into a transcription the chat pipeline can consume.

    Priority: explicit client transcript → named fixture. Language is detected
    from the text when not supplied. Raises ValueError if neither is usable.
    """
    if transcript and transcript.strip():
        text = transcript.strip()
        lang = (language or detect_language(text)).lower()
        conf = float(confidence) if confidence is not None else 1.0
        return AsrResult(text, _clamp(conf), _norm_lang(lang), "client",
                         detail="client-supplied transcription (Team C ASR contract)")

    if fixture_id:
        fx = _load_fixtures().get(fixture_id)
        if not fx:
            raise ValueError(f"unknown ASR fixture_id: {fixture_id!r} (have: {list_fixtures()})")
        text = fx["transcript"]
        lang = (language or fx.get("language") or detect_language(text)).lower()
        conf = float(confidence if confidence is not None else fx.get("confidence", 1.0))
        return AsrResult(text, _clamp(conf), _norm_lang(lang), "fixture",
                         detail=f"canned fixture {fixture_id!r} (Team C pipeline not importable)")

    raise ValueError("transcribe() needs either a non-empty `transcript` or a `fixture_id`")


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _norm_lang(lang: str) -> str:
    return "dz" if lang in ("dz", "dzo", "dzo_tibt") else "en"


if __name__ == "__main__":
    print("fixtures:", list_fixtures())
    print(transcribe(transcript="How do I register my child's birth?").to_dict())
    print(transcribe(fixture_id="dz_tax_2026").to_dict())
