"""
═══════════════════════════════════════════════════════════════════════
  tts_dz.py — live Dzongkha text-to-speech (MMS-TTS-dzo) with an in-memory cache.

  Browsers have NO Dzongkha voice, so the server synthesizes Dzongkha audio for
  ANY text (conversational answers, not just pre-recorded sections). This is the
  permanent replacement for the pre-generated section clips.

  Flow: the pipeline calls register_text(dz_text) -> short hash; the UI then GETs
  /api/tts/<hash>, which calls get_wav(hash) to synthesize (once) and cache the
  WAV bytes. Synthesis is lazy so the chat response returns fast.

  Requires torch + transformers (installed in the container via the Dockerfile).
  If they are absent, available() is False and the caller serves no audio.

  Quality/sovereignty upgrade: swap MODEL for a fine-tuned VITS voice (or human
  recordings) — the register_text()/get_wav() interface stays identical.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import hashlib
import io
import threading

MODEL = "facebook/mms-tts-dzo"

try:
    import numpy as np
    import scipy.io.wavfile as _wavf
    import torch
    from transformers import AutoTokenizer, VitsModel
    _OK = True
except Exception:  # pragma: no cover - dependency optional
    _OK = False

_lock = threading.Lock()
_tok = None
_model = None
_TEXT: dict = {}        # hash -> text (registered, awaiting synthesis)
_WAV: dict = {}         # hash -> wav bytes (synthesized cache)
_MAX_CACHE = 256


def available() -> bool:
    return _OK


def _load():
    global _tok, _model
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _model = VitsModel.from_pretrained(MODEL)
    return _tok, _model


def register_text(text: str):
    """Register text for later synthesis; returns a short hash id (or None if TTS off)."""
    if not _OK or not text:
        return None
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    _TEXT[h] = text
    return h


def get_wav(h: str):
    """Return WAV bytes for a registered hash, synthesizing once and caching. None if unknown."""
    if not _OK:
        return None
    if h in _WAV:
        return _WAV[h]
    text = _TEXT.get(h)
    if not text:
        return None
    with _lock:
        if h in _WAV:
            return _WAV[h]
        tok, model = _load()
        inputs = tok(text, return_tensors="pt")
        with torch.no_grad():
            wave = model(**inputs).waveform.squeeze().cpu().numpy()
        buf = io.BytesIO()
        _wavf.write(buf, model.config.sampling_rate, (wave * 32767).astype(np.int16))
        data = buf.getvalue()
        if len(_WAV) >= _MAX_CACHE:
            _WAV.clear()
        _WAV[h] = data
    return data
