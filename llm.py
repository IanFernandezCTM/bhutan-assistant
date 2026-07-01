"""
═══════════════════════════════════════════════════════════════════════
  llm.py — provider-agnostic, OpenAI-compatible LLM client.  THE SWAP POINT.

  The app talks to ONE OpenAI-compatible /v1/chat/completions endpoint via
  three environment variables:

      LLM_BASE_URL   https://api.deepinfra.com/v1/openai   (live GCP demo, hosted Qwen3-32B)
                     http://localhost:8000/v1               (on-prem / GCP-GPU vLLM, same weights)
      LLM_API_KEY    <provider key>   ->   "EMPTY" for a local vLLM server
      LLM_MODEL      Qwen/Qwen3-32B    (the SAME open weights in both places)

  Recommended model: Qwen/Qwen3-32B (open weights) — so the live demo runs the
  EXACT checkpoint the government will later host on its own GPU. Moving fully
  local (data-sovereign) is then a change of LLM_BASE_URL, not a rewrite.
  See LOCAL_FIRST_PLAN.md.

  Degrades gracefully: if the `openai` SDK is missing or LLM_BASE_URL/LLM_MODEL
  are unset, is_configured() is False and app.py uses the offline keyword
  fallback — so the app still boots with zero configuration.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

LLM_BASE_URL    = os.environ.get("LLM_BASE_URL", "").strip()
LLM_API_KEY     = os.environ.get("LLM_API_KEY", "").strip()
LLM_MODEL       = os.environ.get("LLM_MODEL", "").strip()
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2") or "0.2")
LLM_TIMEOUT     = float(os.environ.get("LLM_TIMEOUT", "60") or "60")

try:
    from openai import OpenAI
    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    OpenAI = None  # type: ignore
    _SDK_AVAILABLE = False

_client = None


def is_configured() -> bool:
    """True when a real OpenAI-compatible endpoint is wired up and usable."""
    return bool(_SDK_AVAILABLE and LLM_BASE_URL and LLM_MODEL)


def provider_label() -> str:
    """Short label for logs / the dev pipeline panel, e.g. 'api.deepinfra.com :: Qwen/Qwen3-32B'."""
    if not LLM_BASE_URL:
        return "none"
    host = LLM_BASE_URL.split("//")[-1].split("/")[0]
    return f"{host} :: {LLM_MODEL}"


def sdk_available() -> bool:
    return _SDK_AVAILABLE


def _get_client():
    global _client
    if _client is None:
        if not _SDK_AVAILABLE:
            raise RuntimeError("openai SDK not installed (pip install openai)")
        # api_key 'EMPTY' is the convention for a keyless local vLLM server.
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "EMPTY",
                         timeout=LLM_TIMEOUT)
    return _client


def chat(messages: List[Dict[str, str]], temperature: Optional[float] = None,
         max_tokens: int = 1024, json_mode: bool = False) -> str:
    """Single chat-completions call. Returns the assistant message content (string).

    json_mode asks the endpoint for a JSON object; if the provider doesn't support
    response_format we transparently retry without it (the caller parses defensively).
    """
    client = _get_client()
    kwargs = dict(
        model=LLM_MODEL,
        messages=messages,
        temperature=LLM_TEMPERATURE if temperature is None else temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        try:
            resp = client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs)
            return resp.choices[0].message.content or ""
        except Exception:
            pass  # provider may not support response_format → fall through
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


if __name__ == "__main__":
    print(f"configured={is_configured()}  sdk={_SDK_AVAILABLE}  provider={provider_label()}")
    if is_configured():
        print(chat([{"role": "user", "content": "Say 'hello from the local model' in 5 words."}],
                   max_tokens=32))
