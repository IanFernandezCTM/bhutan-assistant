"""
═══════════════════════════════════════════════════════════════════════
  feedback.py — lightweight, sovereign feedback capture.

  Each submission records THREE things (see the UI's feedback form):
    1. the citizen's input prompt,
    2. the "behind-the-scenes" pipeline snapshot (what each stage did),
    3. the user's own written feedback (+ a quick helpful / needs-work rating).

  Storage is a plain JSON-Lines file — no database, no external service, so it
  runs on the government's own hardware. An in-memory cache backs the dev-mode
  viewer so "show all feedback" works instantly even where the container
  filesystem is ephemeral (e.g. Cloud Run scales to zero).

  Path override:  FEEDBACK_PATH env var (default: feedback_log.jsonl beside app).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List

FEEDBACK_PATH = Path(os.environ.get(
    "FEEDBACK_PATH", str(Path(__file__).resolve().parent / "feedback_log.jsonl")))

_ITEMS: List[Dict] = []
_LOADED = False


def _load() -> None:
    """Read any previously-saved feedback once (best-effort)."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        if FEEDBACK_PATH.exists():
            for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    _ITEMS.append(json.loads(line))
                except Exception:
                    pass  # skip a corrupt line, keep the rest
    except Exception:
        pass


def record(entry: Dict) -> Dict:
    """Normalize + store one feedback submission; returns the stored item."""
    _load()
    item = {
        "id": uuid.uuid4().hex[:10],
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": str(entry.get("trace_id") or ""),
        "prompt": str(entry.get("prompt") or ""),
        "answer": str(entry.get("answer") or ""),
        "language": str(entry.get("language") or ""),
        "rating": str(entry.get("rating") or ""),      # "up" | "down" | ""
        "comment": str(entry.get("comment") or ""),
        "pipeline": entry.get("pipeline") if isinstance(entry.get("pipeline"), dict) else {},
    }
    _ITEMS.append(item)
    try:
        with FEEDBACK_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception:
        pass  # keep the in-memory copy even if the disk write fails
    return item


def all_feedback() -> List[Dict]:
    """All submissions, newest first (for the dev-mode viewer)."""
    _load()
    return list(reversed(_ITEMS))


def count() -> int:
    _load()
    return len(_ITEMS)
