"""
═══════════════════════════════════════════════════════════════════════
  NLP ENRICHMENT LAYER
  Bilingual language detection + structured entity extraction.

  Source / credit:
    Adapted from team_a_nlp/intent_classifier.py — the bilingual
    (English + Dzongkha) IntentClassifier written by ghimire lokraj,
    part of Team A's NLP track. Supabase/Ollama RAG ingestion work in
    that same folder is by Vaibhavi.

  Why this exists:
    The prototype's Gemini classifier answers FOUR dimensions
    (in_scope / safety / request_type / service) but is English-only
    and pulls no structured data out of the message. lokraj's classifier
    already solved both problems. Rather than duplicate that effort, we
    reuse his language-detection + entity-extraction logic verbatim and
    bolt it on as an enrichment pass after the Gemini call.

  This module is intentionally dependency-free (regex only), so it adds
  ZERO new packages to requirements.txt and runs on the Render free tier.
═══════════════════════════════════════════════════════════════════════
"""

import re
from typing import Dict


# Dzongkha / Tibetan script lives in the Unicode block U+0F00–U+0FFF.
# (lokraj's heuristic — if any character falls in that range, it's Dzongkha.)
_DZONGKHA_CHARS = re.compile(r"[ༀ-࿿]")


def detect_language(text: str) -> str:
    """Return 'dz' if the text contains Dzongkha script, else 'en'."""
    return "dz" if _DZONGKHA_CHARS.search(text) else "en"


def extract_entities(text: str) -> Dict[str, str]:
    """
    Pull structured fields out of a citizen's message.

    Faithful to lokraj's `_extract_entities` in team_a_nlp — same regexes,
    same Dzongkha keyword triggers — so the credit is real, not cosmetic.
    """
    entities: Dict[str, str] = {}

    # Citizenship ID (CID): 11 digits beginning with 1, e.g. 11503002345
    cid_match = re.search(r"\b(1\d{10})\b", text)
    if cid_match:
        entities["citizenship_id"] = cid_match.group(1)

    # Plot ID: "plot 905", "PL-1234", or the Dzongkha land markers
    plot_match = re.search(
        r"(?:plot|ས་ཆ་|ས་ཆའི་ཨང་)\s*#?\s*([a-zA-Z0-9\-]+)",
        text,
        re.IGNORECASE,
    )
    if plot_match:
        entities["plot_id"] = plot_match.group(1)

    # Tax / reference year: 20xx
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        entities["tax_year"] = year_match.group(1)

    # Document type (English + Dzongkha triggers)
    low = text.lower()
    if "birth" in low or "སྐྱེས་ཚེས་" in text:
        entities["document_type"] = "birth_certificate"
    elif "marriage" in low or "གཉེན་སྦྱོར་" in text:
        entities["document_type"] = "marriage_certificate"

    return entities


def enrich(user_text: str) -> Dict[str, object]:
    """
    Single entry point used by app.py.

    Returns the two dimensions the Gemini classifier does not provide:
      • language  — 'en' or 'dz'
      • entities  — structured fields found in the message (may be empty)
    """
    return {
        "language": detect_language(user_text),
        "entities": extract_entities(user_text),
    }


if __name__ == "__main__":
    # Quick smoke test — mirrors lokraj's original test cases.
    for q in [
        "I want to register my land plot 905",
        "ཁྲལ་ སྤྲོད་ 2026",
        "Where is my CID 11503002345? Birth certificate status?",
        "What documents do I need for a construction permit?",
    ]:
        print(f"{q!r:55} -> {enrich(q)}")
