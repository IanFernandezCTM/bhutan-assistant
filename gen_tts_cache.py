"""
Offline tool — pre-generate Dzongkha section audio with MMS-TTS-dzo.

Browsers have NO Dzongkha voice, so the app speaks Dzongkha by playing these
pre-rendered clips (served from static/audio/). Because Dzongkha answers are the
VERBATIM native section text, one clip per section matches the answer exactly.

Run once (or whenever policy_docs change):
    pip install torch transformers scipy        # NOT needed to run the app, only to regenerate
    python gen_tts_cache.py

Output: static/audio/<doc_base>__<section_key>.wav  +  _fallback.wav
The deployed container only SERVES these files — it does not need torch.

For a production government voice, replace these with a fine-tuned VITS voice or
human-recorded section audio (see ../LOCAL_FIRST_PLAN.md); the filenames stay the same.
"""
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav
import torch
from transformers import AutoTokenizer, VitsModel

import assistant
import rag

MODEL = "facebook/mms-tts-dzo"
OUT = Path(__file__).resolve().parent / "static" / "audio"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"loading {MODEL} ...")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = VitsModel.from_pretrained(MODEL)
    sr = model.config.sampling_rate

    def synth(text: str, path: Path) -> float:
        inp = tok(text, return_tensors="pt")
        with torch.no_grad():
            w = model(**inp).waveform.squeeze().cpu().numpy()
        wav.write(str(path), sr, (w * 32767).astype(np.int16))
        return len(w) / sr

    items = rag._build_side("dz")  # every Dzongkha policy section
    total = 0.0
    for it in items:
        secs = synth(it["text"], OUT / f"{it['base']}__{it['key']}.wav")
        total += secs
        print(f"  {it['base']}__{it['key']}.wav  ({secs:.1f}s)")

    synth(assistant._fallback_text("dz"), OUT / "_fallback.wav")
    print(f"done: {len(items) + 1} clips, {total:.0f}s total → {OUT}")


if __name__ == "__main__":
    main()
