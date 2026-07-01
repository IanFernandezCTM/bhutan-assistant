"""
═══════════════════════════════════════════════════════════════════════
  ROUTING ADAPTER  (Phase 3 integration)

  Routes a request to a downstream agent, preferring REAL Team B components,
  with the prototype's offline regex router as an explicitly-labelled fallback.

  Backends (selected automatically; agent path gated by flag + key):
    • agent[team_b]  — Team B's real LangGraph/ReAct pipeline (team_b.pipeline
                       .TeamBPipeline). ONLY when USE_TEAM_B_AGENT=1 AND
                       GROQ_API_KEY is set. Imported LAZILY inside a guard
                       (team_b.langgraph_agent.config builds Groq clients at
                       import time and would crash on a keyless free tier).
    • rule[team_b]   — Team B's real rule router
                       (team_b.routing_module.intent_router.route_intent),
                       imported if the package is present (monorepo). stdlib-only,
                       no API key.
    • rule[inline]   — the prototype's vendored copy (team_b_routing.route_intent),
                       the OFFLINE FALLBACK that always works on the deploy repo.

  All backends return the same routing dict shape the UI already renders:
      {agent, intent, confidence, slots, matched_keywords?, reason?}
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# The inline regex router is always importable (vendored in the prototype).
from team_b_routing import route_intent as _inline_route_intent

# Best-effort: APPEND the repo root so Team B's package is importable in the
# monorepo WITHOUT shadowing the prototype's own modules (the repo root also has
# an unrelated app.py). On the deploy repo this points above the app root where
# no team_b/ exists, so the import simply fails and we fall back.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

# Detect Team B's real rule router (monorepo only; stdlib-only, no key).
try:  # pragma: no cover - environment dependent
    from team_b.routing_module.intent_router import route_intent as _team_b_route_intent

    TEAM_B_RULE_AVAILABLE = True
except Exception:
    _team_b_route_intent = None
    TEAM_B_RULE_AVAILABLE = False


@dataclass
class RouteResult:
    routing: Dict           # {agent, intent, confidence, slots, ...} — UI-compatible
    backend: str            # which backend served (agent[team_b] | rule[team_b] | rule[inline])
    detail: str = ""        # note for logs / dev-mode UI
    agent_response: Optional[str] = None   # text from the real LangGraph agent, if any
    team_b_rule_available: bool = field(default=TEAM_B_RULE_AVAILABLE)


def _agent_enabled() -> bool:
    return os.environ.get("USE_TEAM_B_AGENT", "0").strip().lower() in ("1", "true", "yes") \
        and bool(os.environ.get("GROQ_API_KEY", "").strip())


def _rule_route(text: str, trace_id: str) -> RouteResult:
    """Prefer Team B's real rule router; fall back to the inline vendored copy."""
    if TEAM_B_RULE_AVAILABLE and _team_b_route_intent is not None:
        try:
            result = _team_b_route_intent(text, trace_id)
            routing = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            return RouteResult(routing, "rule[team_b]", detail="Team B routing_module.intent_router")
        except Exception as exc:
            # fall through to inline copy
            return RouteResult(_inline_route_intent(text), "rule[inline]",
                               detail=f"team_b rule router failed ({type(exc).__name__}); used inline copy")
    return RouteResult(_inline_route_intent(text), "rule[inline]",
                       detail="offline regex router (vendored copy of Team B routing_module)")


def _try_agent_route(text: str, trace_id: str) -> Optional[RouteResult]:
    """Lazily try Team B's real LangGraph pipeline. Returns None to signal fallback."""
    try:  # pragma: no cover - requires GROQ_API_KEY + heavy deps
        from team_b.pipeline import TeamBPipeline  # lazy import INSIDE the guard

        out = TeamBPipeline().run(text, user_id="prototype", trace_id=trace_id)
        route = out.get("route") if isinstance(out, dict) else None
        if hasattr(route, "to_dict"):
            routing = route.to_dict()
        elif isinstance(route, dict):
            routing = route
        else:
            routing = {}
        # ensure UI-required keys exist
        routing.setdefault("agent", "team_b_agent")
        routing.setdefault("intent", (out.get("classification") or {}).get("intent", "agent"))
        routing.setdefault("confidence", 0.0)
        routing.setdefault("slots", {})
        return RouteResult(routing, "agent[team_b]",
                           detail="Team B LangGraph/ReAct pipeline (Groq)",
                           agent_response=str(out.get("agent_response") or "") or None)
 #    except Exception as exc:
    except Exception:
        return None  # caller logs and falls back to rule router


def route(text: str, trace_id: str = "init-000") -> RouteResult:
    """Public entry point used by app.py."""
    if _agent_enabled():
        agent_result = _try_agent_route(text, trace_id)
        if agent_result is not None:
            return agent_result
        # fall through: agent requested but unavailable/failed
        rr = _rule_route(text, trace_id)
        rr.detail = "USE_TEAM_B_AGENT set but agent unavailable → " + rr.detail
        rr.backend = rr.backend + " (agent fallback)"
        return rr
    return _rule_route(text, trace_id)


if __name__ == "__main__":
    for s in [
        "I want to register a new business in Thimphu.",
        "What documents do I need for a permit renewal?",
        "Which clinic in Paro can I visit for a doctor appointment?",
    ]:
        r = route(s, trace_id="TRC-TEST0001")
        print(f"[{r.backend}] {s[:40]!r:42} -> agent={r.routing.get('agent')} "
              f"intent={r.routing.get('intent')} ({r.detail})")
