"""Pytest config for the prototype's own tests.

The repo ROOT contains an unrelated Streamlit `app.py`; the prototype contains
the Flask `app.py`. pytest's repo-level config can put the repo root ahead of
the prototype on sys.path, so `import app` would grab the wrong one. We force
the prototype dir to the FRONT and drop the repo root (the integration modules
re-append it lazily, so sibling packages like team_b still resolve).
"""
import os
import sys
from pathlib import Path

_PROTO = str(Path(__file__).resolve().parents[1])
_ROOT = str(Path(__file__).resolve().parents[2])

# Drop repo root / cwd / PYTHONPATH entries so they can't shadow the prototype's modules…
for p in (_ROOT, ".", ""):
    while p in sys.path:
        sys.path.remove(p)
# …and pin the prototype dir first.
while _PROTO in sys.path:
    sys.path.remove(_PROTO)
sys.path.insert(0, _PROTO)

# Deterministic flags for the suite (no API key → keyword classifier path).
os.environ.setdefault("RAG_BACKEND", "docs")
os.environ.setdefault("EMIT_CANONICAL_INTENT", "1")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("USE_TEAM_B_AGENT", None)
