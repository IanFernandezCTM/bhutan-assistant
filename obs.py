"""
═══════════════════════════════════════════════════════════════════════
  OBSERVABILITY: structured JSON logging + trace_id  (Phase 3 integration)

  Standardises on Team D's structured-logging schema
  (team_d_integrations/service_logging — LogEntry):
      timestamp · level · trace_id · service · event · message · metadata

  • If Team D's service_logging package is importable (monorepo + pydantic),
    we DELEGATE to its log_json / generate_trace_id so logs are byte-identical
    to Team D's. Otherwise we use a field-identical LOCAL fallback (zero deps),
    which is what actually ships on the Render free tier (pydantic is not a
    prototype dependency).
  • Team D's request middleware is FastAPI-only, so the Flask request shim
    (mint/accept X-Trace-ID per request, echo it on the response) lives here.

  trace_id format: 'TRC-XXXXXXXX' (Team D convention; inbound UUIDs also accepted).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import contextvars
import json
#import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SERVICE_NAME = "team_a_prototype"
TRACE_HEADER = "X-Trace-ID"
_LOG_DIR = Path(__file__).resolve().parent / "logs" / "team_a"
_TRACE_RE = re.compile(r"^TRC-[0-9A-F]{8}$|^[0-9a-fA-F-]{8,36}$")

_current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="unknown")

# ── Optional delegation to Team D's real logger (monorepo + pydantic) ──
# APPEND (don't front-insert) so we never shadow the prototype's own modules.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
try:  # pragma: no cover - environment dependent
    from team_d_integrations.service_logging import generate_trace_id as _td_gen_trace_id
    from team_d_integrations.service_logging import log_json as _td_log_json

    TEAM_D_LOGGING_AVAILABLE = True
except Exception:
    _td_gen_trace_id = None
    _td_log_json = None
    TEAM_D_LOGGING_AVAILABLE = False


def generate_trace_id() -> str:
    if TEAM_D_LOGGING_AVAILABLE and _td_gen_trace_id is not None:
        try:
            return _td_gen_trace_id()
        except Exception:
            pass
    return "TRC-" + uuid.uuid4().hex[:8].upper()


def validate_trace_id(value: Optional[str]) -> bool:
    return bool(value and _TRACE_RE.match(value.strip()))


def get_trace_id() -> str:
    return _current_trace_id.get()


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _current_trace_id.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    try:
        _current_trace_id.reset(token)
    except Exception:
        pass


def _local_log_json(*, level: str, service: str, message: str, trace_id: Optional[str],
                    event: str, metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "trace_id": trace_id or get_trace_id() or "unknown",
        "service": service,
        "event": event,
        "message": message,
        "metadata": {**(metadata or {}), **kwargs},
    }
    # stdout: ensure_ascii=True keeps Windows cp1252 consoles happy; Render is UTF-8.
    print(json.dumps(entry))
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(_LOG_DIR / f"{date}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never break a request
    return entry


def log_event(level: str, event: str, message: str, trace_id: Optional[str] = None,
              **metadata: Any) -> Dict:
    """Emit one structured log line (Team D schema). Never raises."""
    tid = trace_id or get_trace_id()
    if TEAM_D_LOGGING_AVAILABLE and _td_log_json is not None:
        try:  # pragma: no cover - requires team_d + pydantic
            entry = _td_log_json(level=level, service=SERVICE_NAME, message=message,
                                 trace_id=tid, event=event, metadata=metadata)
            return entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
        except Exception:
            pass
    return _local_log_json(level=level, service=SERVICE_NAME, message=message,
                           trace_id=tid, event=event, metadata=metadata)


def backend_name() -> str:
    return "team_d.service_logging" if TEAM_D_LOGGING_AVAILABLE else "local(team-d-schema)"


# ── Flask request shim (Team D has no Flask middleware) ──
def init_app(app, service_name: str = SERVICE_NAME) -> None:
    """Register before/after request hooks that mint/accept + echo a trace_id."""
    from flask import g, request

    @app.before_request
    def _start_trace():  # noqa: ANN202
        inbound = request.headers.get(TRACE_HEADER, "").strip()
        trace_id = inbound if validate_trace_id(inbound) else generate_trace_id()
        g.trace_id = trace_id
        g.trace_token = set_trace_id(trace_id)

    @app.after_request
    def _end_trace(response):  # noqa: ANN001, ANN202
        trace_id = getattr(g, "trace_id", None)
        if trace_id:
            response.headers[TRACE_HEADER] = trace_id
        token = getattr(g, "trace_token", None)
        if token is not None:
            reset_trace_id(token)
        return response


if __name__ == "__main__":
    tid = generate_trace_id()
    set_trace_id(tid)
    print("backend:", backend_name(), "| trace_id:", tid, "| valid:", validate_trace_id(tid))
    log_event("INFO", "demo.event", "hello from obs.py", stage="smoke-test", n=1)
