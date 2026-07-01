"""
═══════════════════════════════════════════════════════════════════════
  assistant.py — the LLM-first, grounded answering engine.

  ONE call replaces the old four-call classifier + template engine + separate
  translator: given the user's message and the retrieved bilingual policy
  context, the model returns a grounded answer IN THE USER'S LANGUAGE, plus the
  classification (scope / safety / service) as a by-product.

  Dzongkha strategy (research-driven — see LOCAL_FIRST_PLAN.md): never
  free-generate or machine-translate Dzongkha facts. The model is told to QUOTE
  the human-authored native Dzongkha passage from the context, copy numbers/IDs
  verbatim, cite sources, and ABSTAIN when the context has no answer.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

import llm

SERVICES = ["permits", "health", "business", "ndi", "civil_registration",
            "education", "taxes", "general"]

SYSTEM_PROMPT = """You are the Bhutan Public Services Assistant, an official government helper.
Your answer will be read aloud (and, for Dzongkha users, machine-translated first), so write a
short, warm, CONVERSATIONAL reply in ENGLISH — 1 to 3 short sentences, no headings or bullet
dumps. Lead with the direct answer.

Each CONTEXT block is tagged with an id like [S1], [S2] with the official policy text.

FOLLOW THESE RULES EXACTLY:
1. GROUNDING — Answer ONLY using the CONTEXT. Never use outside knowledge or guess. If the CONTEXT
   does not contain the answer, set "abstained" true, "answer_block" null, and say you don't have
   that official information yet and to contact the relevant office/helpline.
2. EXACT FACTS — Copy numbers, amounts, dates, fees, and ID numbers exactly as they appear in the
   CONTEXT; never round or invent them. Answer the SPECIFIC thing asked — if a section has several
   related figures (e.g. a late-filing PENALTY vs a late-payment INTEREST rate), give exactly the
   one requested, not a neighbouring figure.
3. SELECT — Set "answer_block" to the id (e.g. "S2") of the single block that best answers, unless
   abstaining.
4. SCOPE — If the request is not about a Bhutanese government public service, set "in_scope" false
   and politely decline.
5. SAFETY — Never give medical diagnosis/treatment, legal, or financial advice; set "safe" false
   and refer the user to the proper office/professional.
6. LIVE RECORD — A "LIVE RECORD" block may appear below the CONTEXT. It is an authoritative
   lookup of the citizen's own government record and OVERRIDES the grounding rule for that answer:
   • If it is tagged [IDENTITY VERIFIED], answer the user's question about THEIR record using those
     exact values — copy every status, amount, date, and ID verbatim. Set "abstained" false.
   • If it is tagged [IDENTITY NOT VERIFIED], reveal NO details from the record. Briefly explain that,
     for privacy, you can only share it with the record's owner, and ask them to confirm their own
     CID or visit the office. Set "safe" true, "abstained" false.
   • If it is tagged [NOT FOUND], tell them no matching record was found and to re-check the reference.

Return ONLY a JSON object with exactly these fields:
{"in_scope": boolean, "safe": boolean, "service": one of [SERVICES], "answer": string (English,
conversational, 1-3 sentences), "answer_block": string id like "S2" or null,
"sources_used": [string], "confidence": number between 0 and 1, "abstained": boolean}
""".replace("[SERVICES]", ", ".join(SERVICES))


def _format_context(bundle: List[Dict]) -> str:
    if not bundle:
        return "(no relevant policy text was found)"
    blocks = []
    for c in bundle:
        block = (f"[{c['_id']}] source={c['source']} · {c.get('title', '')}\n"
                 f"EN: {(c.get('en_text') or '').strip()}")
        if c.get("dz_text"):
            block += f"\nDZ: {c['dz_text'].strip()}"
        blocks.append(block)
    return "\n\n".join(blocks)


def _extract_json(text: str) -> Dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])
    return json.loads(text)


def _fallback_text(language: str) -> str:
    if language == "dz":
        return ("དགོངས་དག འདི་གི་སྐོར་ལས་ ད་ལྟོ་ ང་ལུ་ ངོ་མའི་གནས་ཚུལ་མེད། "
                "ཁྱོད་རའི་འབྲེལ་ཡོད་ཡིག་ཚང་ལུ་ འབྲེལ་བ་འཐབ་གནང་།")
    return ("I'm sorry, I don't have official information on that yet. "
            "Please contact the relevant office or call the helpline (17).")


def answer(user_text: str, language: str, bundle: List[Dict],
           transaction: Optional[str] = None) -> Dict:
    """Run the single grounded call. Returns a normalized dict the pipeline consumes.

    For Dzongkha, the model only SELECTS the relevant block; we substitute the native
    Dzongkha text of that block VERBATIM (retrieve-and-quote), because the model cannot be
    trusted to generate correct Dzongkha. English answers stay model-composed.

    `transaction`, when provided, is an authoritative "LIVE RECORD" block from an in-process
    government lookup (see transactions.py). It is appended after the CONTEXT and, per rule 6,
    overrides grounding for that answer — this is how the sovereign, single-call pipeline gains
    Team B's transactional power without a second model call or any external service.
    """
    for i, c in enumerate(bundle):
        c["_id"] = f"S{i + 1}"
    by_id = {c["_id"]: c for c in bundle}

    context = _format_context(bundle)
    live = f"\n\n{transaction}" if transaction else ""
    user_msg = (f"LANGUAGE: {language}\n\nCONTEXT:\n{context}{live}\n\n"
                f"QUESTION: {user_text}\n\nReturn only the JSON object.")
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}]

    raw = llm.chat(messages, json_mode=True, max_tokens=1024)

    try:
        data = _extract_json(raw)
    except Exception:
        # Model returned prose instead of JSON — keep the text, flag it, stay safe.
        return {
            "in_scope": True, "safe": True, "service": "general",
            "answer": (raw or "").strip() or _fallback_text(language),
            "sources_used": [c["source"] for c in bundle],
            "confidence": 0.3, "abstained": not bool(bundle), "parse_error": True,
        }

    # Normalize / harden the fields downstream code relies on.
    data["answer"] = str(data.get("answer") or _fallback_text(language))
    data["service"] = data.get("service") if data.get("service") in SERVICES else "general"
    data["in_scope"] = bool(data.get("in_scope", True))
    data["safe"] = bool(data.get("safe", True))
    data["abstained"] = bool(data.get("abstained", False))
    try:
        data["confidence"] = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        data["confidence"] = 0.0

    # Sources are always derived from the chosen section (a real filename) — never the model's
    # self-reported list, which can leak block ids like "S2".
    chosen = by_id.get(data.get("answer_block")) or (bundle[0] if bundle else None)
    if chosen and not data["abstained"]:
        data["sources_used"] = [chosen["source"]]
        data["chosen_block"] = {"source": chosen["source"], "title": chosen.get("title"),
                                "dz_text": chosen.get("dz_text", "")}
    else:
        data["sources_used"] = []
    return data


if __name__ == "__main__":
    import rag
    if not llm.is_configured():
        print("LLM not configured — set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL to try this.")
    else:
        q = "How much is the late filing penalty for income tax?"
        out = answer(q, "en", rag.retrieve_grounding(q))
        print(json.dumps(out, ensure_ascii=False, indent=2))
