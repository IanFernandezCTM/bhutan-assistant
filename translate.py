"""
═══════════════════════════════════════════════════════════════════════
  translate.py — pluggable EN<->DZ machine translation with number protection.

  Used for the conversational Dzongkha path (English-pivot): the LLM answers
  conversationally in English, then we translate that answer to Dzongkha and
  speak it (see tts_dz.py). This mirrors Team C's DZ_tts.py approach.

  Backend (env TRANSLATE_BACKEND, default "google"):
    • google — Google Cloud Translation via Application Default Credentials
               (on Cloud Run = the runtime service account; no key to manage).
               Requires the Cloud Translation API enabled + roles/cloudtranslate.user,
               and the `google-cloud-translate` package.
    • (none) — if unavailable, available() is False and the caller falls back to
               quoting the verbatim native Dzongkha passage instead.

  NUMBER PROTECTION: digits/amounts are wrapped in <span translate="no"> before
  translation (HTML mode), so Google never alters them; afterwards they are
  converted to Dzongkha numerals so the TTS voice pronounces them. This keeps
  facts/fees/dates exact — the one correctness property a government needs —
  even though the surrounding wording is machine-translated.

  Swap-in path for data sovereignty / quality: replace the backend with the
  CST Bhutan NMT or a local NLLB model; the to_english()/to_dzongkha() interface
  stays the same.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import html
import os
import re

BACKEND = os.environ.get("TRANSLATE_BACKEND", "google").strip().lower()

try:
    from google.cloud import translate_v2 as _gct
    _GCT_AVAILABLE = True
except Exception:  # pragma: no cover - dependency optional
    _gct = None
    _GCT_AVAILABLE = False

_client = None
_EN_TO_DZ_DIGIT = {str(i): d for i, d in enumerate("༠༡༢༣༤༥༦༧༨༩")}
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def available() -> bool:
    return BACKEND == "google" and _GCT_AVAILABLE


def backend_label() -> str:
    return f"google-cloud-translate" if available() else f"{BACKEND}(unavailable)"


def _cli():
    global _client
    if _client is None:
        _client = _gct.Client()
    return _client


def _to_dz_numerals(s: str) -> str:
    return "".join(_EN_TO_DZ_DIGIT.get(ch, ch) for ch in s)


def to_english(text: str) -> str:
    """Translate a (Dzongkha) question to English for retrieval + generation. Best-effort."""
    if not available() or not text:
        return text
    try:
        res = _cli().translate(text, source_language="dz", target_language="en", format_="text")
        return res.get("translatedText") or text
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"[translate to_english error: {type(exc).__name__}: {exc}]")
        return text


def to_dzongkha(text: str):
    """Translate an English answer to Dzongkha, preserving numbers verbatim.
    Returns None if translation is unavailable/failed (caller falls back)."""
    if not available() or not text:
        return None
    try:
        escaped = html.escape(text)
        protected = _NUM_RE.sub(lambda m: f'<span translate="no">{m.group(0)}</span>', escaped)
        res = _cli().translate(protected, source_language="en", target_language="dz", format_="html")
        out = res.get("translatedText") or ""
        out = re.sub(r"</?span[^>]*>", "", out)   # drop the protection tags
        out = html.unescape(out)
        out = _NUM_RE.sub(lambda m: _to_dz_numerals(m.group(0)), out)  # speakable numerals
        return out.strip() or None
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"[translate to_dzongkha error: {type(exc).__name__}: {exc}]")
        return None
