"""
═══════════════════════════════════════════════════════════════════════
  BHUTAN VOICE-FIRST PUBLIC SERVICE ASSISTANT — Flask Backend
  Wraps Team A's classifier + conversation engine in a web API.

  TIER 1 PATCH APPLIED — based on Team A's Week-3 findings:
    1. Chain-of-thought classifier
       95.1% benchmark accuracy vs. 85.4% for single-call.
    2. Schema-constrained output — eliminates the `service=unknown`
       failure mode the team documented.
    3. Expanded label set:
         + facility_lookup     (vs. office_location confusion)
         + ndi, civil_registration, education, taxes
    4. Per-dimension short-circuiting — out_of_scope skips 3 calls,
       unsafe skips 2 calls. Cost optimisation per Team A's design.

  NOT in this patch (deliberate, to keep Render footprint small):
    • BART zero-shot first gate — needs torch + 1.6 GB model.
      Will fit on Standard tier (2 GB RAM) but not free/starter.
    • Vector-DB knowledge retrieval — Tier 2 work, see report § 6.
═══════════════════════════════════════════════════════════════════════
"""

import os
import json
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from flask import Flask, request, jsonify, render_template, g

# Bilingual language detection + entity extraction, reused from the
# team_a_nlp track (Team A). See nlp_enrichment.py for credit.
from nlp_enrichment import enrich

# Phase-3 integration layers (see INTEGRATION_PLAN.md). Each prefers a REAL
# team component when present and falls back safely so the app stays
# deployable on the Render free tier with zero API keys.
import rag                 # RAG retrieval over real policy docs (Team A NLP), flag-controlled
import intent_schema       # 4-dim → canonical nlp_intent_schema_v2 (Team D)
import routing_adapter     # real Team B router / LangGraph agent, regex fallback
import asr_adapter         # Team C voice-input adapter (+ fixtures)
import obs                 # structured JSON logging + trace_id (Team D schema)

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")

# Integration feature flags (all default to the safe/offline behaviour;
# see INTEGRATION_PLAN.md). RAG_BACKEND is also read inside rag.py.
RAG_BACKEND           = os.environ.get("RAG_BACKEND", "kb").strip().lower()
EMIT_CANONICAL_INTENT = os.environ.get("EMIT_CANONICAL_INTENT", "1").strip().lower() in ("1", "true", "yes")


# ═══════════════════════════════════════════════════════════════════
# ✏️  EDIT ME — LABEL CATEGORIES (Team A's expanded set)
# ═══════════════════════════════════════════════════════════════════
IN_SCOPE_LABELS = ["in_scope", "out_of_scope"]
SAFETY_LABELS   = ["safe", "unsafe"]

REQUEST_TYPES = [
    "document_inquiry",       # what documents do I need?
    "facility_lookup",        # nearest hospital/BHU/centre (NEW)
    "office_location",        # address of a govt admin office
    "status_check",           # check application status
    "application_start",      # start a new application
    "eligibility_check",      # am I eligible?
    "general_info",           # explain / general question
    "other",
]

SERVICES = [
    "permits",                # timber, sand, stone, construction permits
    "health",                 # hospitals, BHUs, vaccinations
    "business",               # business registration, trade license
    "ndi",                    # National Digital Identity   (NEW)
    "civil_registration",     # birth, death, marriage cert (NEW)
    "education",              # schools, scholarships       (NEW)
    "taxes",                  # tax filing, BIT, PIT        (NEW)
    "general",                # catch-all
]


# ═══════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════
@dataclass
class ClassificationResult:
    label: str
    confidence: float
    reasoning: str = ""   # CoT trace, kept server-side for debugging


# ═══════════════════════════════════════════════════════════════════
# CLASSIFIERS
# ═══════════════════════════════════════════════════════════════════
class BaseClassifier:
    def classify(self, user_text: str) -> Dict[str, ClassificationResult]:
        raise NotImplementedError


class GeminiClassifier(BaseClassifier):
    """
    Task-decomposed chain-of-thought classifier.

    Each of the four dimensions is handled by its own Gemini call with:
      • Chain-of-thought reasoning forced via the schema (the model
        must produce `reasoning` before `label`).
      • 3 few-shot examples covering the dimension's boundary cases.
      • Schema-constrained output — `label` must be in the enum,
        so `service=unknown` and similar failure modes are gone.

    Short-circuits:
      • out_of_scope  → skip safety, request_type, service (3 calls saved)
      • unsafe        → skip request_type, service        (2 calls saved)

    Design: Team A. Benchmark: 95.1% overall accuracy
    on the 36-question labelled test set (`bhutan_classifier_test_set.csv`).
    """

    # ─────────────────────────────────────────────────────────────────
    # ✏️  EDIT ME — FEW-SHOT EXAMPLES (one block per dimension)
    # To improve a single dimension's accuracy without disturbing the
    # others, edit only that dimension's example list.
    # ─────────────────────────────────────────────────────────────────

    IN_SCOPE_FEWSHOT = [
        {
            "request": "How do I apply for a timber permit?",
            "reasoning": "User asks about a forestry permit application — a Bhutanese public service operated by the Department of Forests. Clearly in scope.",
            "label": "in_scope",
            "confidence": 0.99,
        },
        {
            "request": "How to plan tour in Bhutan?",
            "reasoning": "Tour planning is a tourism / commercial activity. While Bhutan has a Department of Tourism, tour planning is normally handled by tour operators, not as a citizen-facing public service. Treat as out-of-scope. (This fixes a misclassification Team A found in testing.)",
            "label": "out_of_scope",
            "confidence": 0.85,
        },
        {
            "request": "Who won the cricket match yesterday?",
            "reasoning": "Sports score — no connection to Bhutanese public services. Out of scope.",
            "label": "out_of_scope",
            "confidence": 1.0,
        },
    ]

    SAFETY_FEWSHOT = [
        {
            "request": "My stomach hurts — do I have cancer?",
            "reasoning": "User is asking for a medical diagnosis. The assistant must not diagnose. Unsafe.",
            "label": "unsafe",
            "confidence": 0.99,
        },
        {
            "request": "Where is the nearest Basic Health Unit?",
            "reasoning": "Pure navigational / informational query about a health facility. Safe.",
            "label": "safe",
            "confidence": 1.0,
        },
        {
            "request": "Can I avoid paying tax by registering my shop as cottage industry?",
            "reasoning": "User asks for specific tax-avoidance advice that would constitute legal/financial guidance. Unsafe.",
            "label": "unsafe",
            "confidence": 0.90,
        },
    ]

    REQUEST_TYPE_FEWSHOT = [
        {
            "request": "What documents do I need for a construction permit?",
            "reasoning": "Document checklist inquiry — the user wants to know what to bring.",
            "label": "document_inquiry",
            "confidence": 0.98,
        },
        {
            "request": "Where is the nearest hospital in Paro?",
            "reasoning": "User asks where a SERVICE FACILITY is. This is facility_lookup, NOT office_location (which is for govt admin offices like MoEA).",
            "label": "facility_lookup",
            "confidence": 0.97,
        },
        {
            "request": "Where is the MoEA office in Thimphu?",
            "reasoning": "User asks for the address of a government administrative office. This is office_location.",
            "label": "office_location",
            "confidence": 0.97,
        },
    ]

    SERVICE_FEWSHOT = [
        {
            "request": "How do I get a timber permit?",
            "reasoning": "Forestry / land-use permit — permits service.",
            "label": "permits",
            "confidence": 0.99,
        },
        {
            "request": "How do I register my child's birth?",
            "reasoning": "Birth registration is handled by the Department of Civil Registration and Census (DCRC) — civil_registration. (This closes a gap Team A found in testing.)",
            "label": "civil_registration",
            "confidence": 0.98,
        },
        {
            "request": "Where can I update my NDI biometric details?",
            "reasoning": "User explicitly references NDI — National Digital Identity service.",
            "label": "ndi",
            "confidence": 0.99,
        },
    ]

    # ─────────────────────────────────────────────────────────────────
    # Per-dimension schemas — enforce enum constraints on label
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _schema(enum_values: List[str]) -> Dict:
        return {
            "type": "object",
            "properties": {
                # Order matters: reasoning first forces CoT before answer.
                "reasoning":  {"type": "string"},
                "label":      {"type": "string", "enum": enum_values},
                "confidence": {"type": "number"},
            },
            "required": ["reasoning", "label", "confidence"],
        }

    def __init__(self, api_key: str, model_name: str = GEMINI_MODEL_NAME):
        if not GENAI_AVAILABLE:
            raise ImportError("google-generativeai not installed.")
        genai.configure(api_key=api_key)
        self.model_name = model_name
        # Model is stateless wrt schema — schema is passed per-call below.
        self.model = genai.GenerativeModel(model_name)

    # ── Public entry point ─────────────────────────────────────────

    def classify(self, user_text: str) -> Dict[str, ClassificationResult]:
        # Step 1: in-scope
        in_scope = self._step_in_scope(user_text)
        if in_scope.label == "out_of_scope":
            return self._short_circuit_out_of_scope(in_scope)

        # Step 2: safety
        safety = self._step_safety(user_text)
        if safety.label == "unsafe":
            return self._short_circuit_unsafe(in_scope, safety)

        # Step 3: request type
        request_type = self._step_request_type(user_text)

        # Step 4: service
        service = self._step_service(user_text)

        return {
            "in_scope":     in_scope,
            "safety":       safety,
            "request_type": request_type,
            "service":      service,
        }

    # ── Per-dimension steps ────────────────────────────────────────

    def _step_in_scope(self, text: str) -> ClassificationResult:
        prompt = self._build_prompt(
            instruction=(
                "Decide whether this user request is about a Bhutanese public service "
                "(in_scope) or not (out_of_scope).\n"
                "IN SCOPE includes: permits, health services, business registration, NDI, "
                "civil registration, taxes, education — services provided by the "
                "Bhutanese government to citizens.\n"
                "OUT OF SCOPE includes: tourism planning, sports, weather, jokes, hotel "
                "bookings, entertainment, general chitchat, and commercial services "
                "not run by the government."
            ),
            examples=self.IN_SCOPE_FEWSHOT,
            user_text=text,
        )
        return self._call_gemini(prompt, self._schema(IN_SCOPE_LABELS), default="in_scope")

    def _step_safety(self, text: str) -> ClassificationResult:
        prompt = self._build_prompt(
            instruction=(
                "Decide whether this request is SAFE for the assistant to answer with "
                "general/procedural information.\n"
                "SAFE: information, navigation, document checklists, office locations.\n"
                "UNSAFE: requests for medical diagnosis, treatment, prescriptions, or "
                "specific legal/financial advice."
            ),
            examples=self.SAFETY_FEWSHOT,
            user_text=text,
        )
        return self._call_gemini(prompt, self._schema(SAFETY_LABELS), default="safe")

    def _step_request_type(self, text: str) -> ClassificationResult:
        prompt = self._build_prompt(
            instruction=(
                "Decide what KIND of help the user is asking for. Pick exactly one label "
                "from the allowed set.\n"
                "Note: `facility_lookup` is for nearest service facilities (hospital, BHU). "
                "`office_location` is for government administrative offices (MoEA, DCRC, etc.)."
            ),
            examples=self.REQUEST_TYPE_FEWSHOT,
            user_text=text,
        )
        return self._call_gemini(prompt, self._schema(REQUEST_TYPES), default="general_info")

    def _step_service(self, text: str) -> ClassificationResult:
        prompt = self._build_prompt(
            instruction=(
                "Decide which government service domain this request belongs to. Pick "
                "exactly one label from the allowed set. Use `general` only if no other "
                "label fits."
            ),
            examples=self.SERVICE_FEWSHOT,
            user_text=text,
        )
        return self._call_gemini(prompt, self._schema(SERVICES), default="general")

    # ── Helpers ────────────────────────────────────────────────────

    def _build_prompt(self, instruction: str, examples: List[Dict],
                      user_text: str) -> str:
        ex_blocks = []
        for ex in examples:
            ex_blocks.append(
                f"Request: \"{ex['request']}\"\n"
                f"Reasoning: {ex['reasoning']}\n"
                f"Answer: {{\"reasoning\": \"{ex['reasoning']}\", "
                f"\"label\": \"{ex['label']}\", \"confidence\": {ex['confidence']}}}"
            )
        examples_section = "\n\n".join(ex_blocks)
        safe_text = user_text.replace('"', "'")
        return (
            f"{instruction}\n\n"
            f"Think step by step. First write your reasoning, then give the label and "
            f"confidence (0.0–1.0).\n\n"
            f"EXAMPLES\n"
            f"{examples_section}\n\n"
            f"NOW CLASSIFY\n"
            f"Request: \"{safe_text}\"\n"
            f"Return only the JSON object."
        )

    def _call_gemini(self, prompt: str, schema: Dict,
                     default: str) -> ClassificationResult:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            data = json.loads(response.text)
            return ClassificationResult(
                label=str(data.get("label", default)),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception as e:
            print(f"[Gemini step error: {type(e).__name__}: {e}]")
            return ClassificationResult(default, 0.0,
                                        reasoning=f"(error: {e})")

    # ── Short-circuit defaults ─────────────────────────────────────

    @staticmethod
    def _short_circuit_out_of_scope(
        in_scope: ClassificationResult,
    ) -> Dict[str, ClassificationResult]:
        skipped = "(not evaluated — short-circuited after out_of_scope)"
        return {
            "in_scope":     in_scope,
            "safety":       ClassificationResult("safe", 1.0, skipped),
            "request_type": ClassificationResult("other", 1.0, skipped),
            "service":      ClassificationResult("general", 1.0, skipped),
        }

    @staticmethod
    def _short_circuit_unsafe(
        in_scope: ClassificationResult,
        safety: ClassificationResult,
    ) -> Dict[str, ClassificationResult]:
        skipped = "(not evaluated — short-circuited after unsafe)"
        return {
            "in_scope":     in_scope,
            "safety":       safety,
            "request_type": ClassificationResult("other", 1.0, skipped),
            "service":      ClassificationResult("general", 1.0, skipped),
        }


class KeywordClassifier(BaseClassifier):
    """No-API fallback — same approach as Team A's original rule-based code."""

    OUT_OF_SCOPE_WORDS = [
        "cricket", "football", "soccer", "movie", "joke", "weather",
        "stock", "forex", "election", "recipe", "song", "celebrity",
        "tour",  # added per Team A testing
    ]
    UNSAFE_WORDS = [
        "diagnose", "diagnosis", "cancer", "tumour", "tumor",
        "treatment", "prescription", "should i take",
        "what disease", "am i sick", "do i have",
    ]
    SERVICE_KEYWORDS = {
        "permits":            ["permit", "license", "licence", "construction",
                               "timber", "stone", "sand"],
        "health":             ["hospital", "doctor", "clinic", "bhu", "vaccin",
                               "medic", "health", "sick", "pain", "pharmacy"],
        "business":           ["business", "register", "registration", "company",
                               "proprietor", "trade", "moea"],
        "ndi":                ["ndi", "national digital identity", "biometric"],
        "civil_registration": ["birth certificate", "death certificate",
                               "marriage", "cid", "citizenship"],
        "education":          ["school", "scholarship", "university", "college"],
        "taxes":              ["tax", "bit", "pit", "rrco", "revenue"],
    }
    TYPE_KEYWORDS = {
        "document_inquiry":  ["document", "papers", "what do i need",
                              "checklist", "requirement"],
        "facility_lookup":   ["nearest hospital", "nearest bhu", "nearest clinic"],
        "office_location":   ["office", "where", "address", "location",
                              "directions"],
        "status_check":      ["status", "track", "reference", "where is my"],
        "application_start": ["apply", "start", "submit", "register", "begin"],
        "eligibility_check": ["eligible", "can i", "qualify", "allowed"],
    }

    def classify(self, text: str) -> Dict[str, ClassificationResult]:
        t = text.lower()
        return {
            "in_scope":     self._in_scope(t),
            "safety":       self._safety(t),
            "service":      self._best_match(t, self.SERVICE_KEYWORDS, "general"),
            "request_type": self._best_match(t, self.TYPE_KEYWORDS, "general_info"),
        }

    def _in_scope(self, t):
        if any(w in t for w in self.OUT_OF_SCOPE_WORDS):
            return ClassificationResult("out_of_scope", 0.8)
        return ClassificationResult("in_scope", 0.7)

    def _safety(self, t):
        if any(w in t for w in self.UNSAFE_WORDS):
            return ClassificationResult("unsafe", 0.8)
        return ClassificationResult("safe", 0.8)

    @staticmethod
    def _best_match(t, mapping, default):
        scores = {k: sum(1 for w in v if w in t) for k, v in mapping.items()}
        if not any(scores.values()):
            return ClassificationResult(default, 0.4)
        best = max(scores, key=scores.get)
        return ClassificationResult(best, min(1.0, scores[best] / 2.0))


# ═══════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE  (unchanged in Tier 1 — Tier 2 swaps this for vector DB)
# ═══════════════════════════════════════════════════════════════════
@dataclass
class KnowledgeChunk:
    id: str
    service: str
    title: str
    text: str
    keywords: Tuple[str, ...]
    source: str


KNOWLEDGE_BASE: List[KnowledgeChunk] = [
    KnowledgeChunk(
        id="prm_construction", service="permits",
        title="Construction Permit — Thimphu",
        text=("For a construction permit in Thimphu you will need:\n"
              "  • CID card (original + photocopy)\n"
              "  • Land Thram (land ownership document)\n"
              "  • No Objection Certificate (NOC) from the landlord\n"
              "  • Completed application form from the dzongkhag office\n"
              "Submit at the Department of Urban Development, "
              "Thadrak, Thimphu (Mon–Fri, 9am–5pm)."),
        keywords=("construction", "permit", "thimphu", "document"),
        source="bhutan_flow_docs/permits",
    ),
    KnowledgeChunk(
        id="prm_timber", service="permits", title="Timber Permit",
        text=("For a timber permit you will need:\n"
              "  • CID card\n"
              "  • Land Thram showing forest plot\n"
              "  • Approval from gewog forest officer\n"
              "  • Completed timber permit form\n"
              "Apply at your local Range Office under the Department of Forests."),
        keywords=("timber", "permit", "forest", "wood"),
        source="bhutan_flow_docs/permits",
    ),
    KnowledgeChunk(
        id="prm_office", service="permits", title="Permit Office — Thimphu",
        text=("Permit office in Thimphu: Department of Urban Development, "
              "Thadrak, Thimphu. Phone: +975-2-xxx-xxxx. "
              "Open Monday to Friday, 9am to 5pm. "
              "Bring original documents and two photocopies."),
        keywords=("office", "location", "where", "address", "thimphu"),
        source="bhutan_flow_docs/permits",
    ),
    KnowledgeChunk(
        id="hlt_facility_thimphu", service="health", title="JDWNRH — Thimphu",
        text=("Nearest hospital in Thimphu: Jigme Dorji Wangchuck National "
              "Referral Hospital (JDWNRH), Gongphel Lam, Thimphu. "
              "Phone: 112 or +975-2-xxx-xxxx. "
              "OPD hours: Mon–Sat 8am–4pm. Emergency: 24 hours."),
        keywords=("hospital", "thimphu", "facility", "nearest"),
        source="bhutan_flow_docs/health",
    ),
    KnowledgeChunk(
        id="hlt_facility_paro", service="health", title="Paro District Hospital",
        text=("Nearest hospital in Paro: Paro District Hospital, Paro town. "
              "Phone: +975-8-xxx-xxxx. Open Mon–Sat, 8am–4pm."),
        keywords=("hospital", "paro", "facility"),
        source="bhutan_flow_docs/health",
    ),
    KnowledgeChunk(
        id="hlt_bhu", service="health", title="Basic Health Units (BHUs)",
        text=("Basic Health Units are present in every block of Bhutan. "
              "Services: outpatient consultation, vaccination, antenatal care, "
              "family planning, referral to district hospitals. "
              "All BHU services are free for Bhutanese citizens."),
        keywords=("bhu", "basic health unit", "free", "vaccination"),
        source="bhutan_flow_docs/health",
    ),
    KnowledgeChunk(
        id="biz_sole", service="business",
        title="Sole Proprietorship Registration",
        text=("To register a sole proprietorship in Bhutan you will need:\n"
              "  • Valid CID card\n"
              "  • Completed application form (from MoEA or moea.gov.bt)\n"
              "  • Proof of address\n"
              "  • Initial capital declaration\n"
              "  • No-objection letter if operating from rented premises"),
        keywords=("business", "register", "sole", "proprietorship"),
        source="bhutan_flow_docs/business",
    ),
    KnowledgeChunk(
        id="biz_processing", service="business", title="License Processing Time",
        text=("If all required information, documents, and clearances are "
              "submitted, the industry license or registration certificate "
              "is issued within one or two working days."),
        keywords=("how long", "processing", "time", "license"),
        source="bhutan_flow_docs/business",
    ),
    KnowledgeChunk(
        id="biz_office", service="business", title="MoEA Office — Thimphu",
        text=("Business registration office: Ministry of Economic Affairs (MoEA), "
              "Tashichhodzong vicinity, Thimphu. Phone: +975-2-xxx-xxxx. "
              "Open Mon–Fri, 9am–5pm. Online: www.moea.gov.bt"),
        keywords=("office", "moea", "thimphu", "where", "business"),
        source="bhutan_flow_docs/business",
    ),
]


def search_kb(user_text: str, service: str, top_k: int = 2):
    t = user_text.lower()
    candidates = [c for c in KNOWLEDGE_BASE if c.service == service]
    if not candidates:
        candidates = KNOWLEDGE_BASE
    scored = []
    for c in candidates:
        score  = sum(1 for kw in c.keywords if kw in t)
        score += sum(1 for word in t.split() if word in c.text.lower()) * 0.1
        scored.append((c, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, s in scored[:top_k] if s > 0] or candidates[:1]


# ═══════════════════════════════════════════════════════════════════
# CONVERSATION ENGINE
# ═══════════════════════════════════════════════════════════════════
@dataclass
class TurnResponse:
    bot_text: str
    sources: List[str]
    step_label: str = ""
    fallback_id: Optional[str] = None
    ref_no: str = ""
    rag_backend: str = "kb"   # which retrieval backend produced the body


class ConversationEngine:
    # Service-specific intros — extended for the new services so they
    # no longer fall through to the generic "Let me share..." line.
    SERVICE_INTROS = {
        "permits":             "Great! Let me guide you through that.",
        "health":              "Of course! Let me guide you to the right information.",
        "business":            "Great! Let me guide you through the process.",
        "ndi":                 "Sure — here is what I can tell you about NDI.",
        "civil_registration":  "Of course — here is what I can tell you about civil registration.",
        "education":           "Happy to help with education services.",
        "taxes":               "Happy to help with tax-related public services.",
        "general":             "Let me share what I can help with.",
    }

    # Services we currently have KB content for. Other services will
    # fall back to the "please contact the office" message until
    # Tier 2 expands the KB.
    SERVICES_WITH_KB = {"permits", "health", "business"}

    def process(self, user_text, classification, rag_result=None):
        ref = f"REF-{uuid.uuid4().hex[:8].upper()}"

        # ── Out-of-scope ──
        if classification["in_scope"].label == "out_of_scope":
            return TurnResponse(
                bot_text=("I can help only with the public services in this assistant. "
                          "I can still help you find the right office, start again, "
                          "or talk to a person."),
                sources=[], fallback_id="FB-03", ref_no=ref, rag_backend="n/a",
            )

        # ── Unsafe (medical / legal / financial advice) ──
        if classification["safety"].label == "unsafe":
            return TurnResponse(
                bot_text=("I can share general public-service information, but I'm not "
                          "able to give medical, legal, or financial advice. "
                          "For personal guidance, please visit the relevant office or "
                          "call the helpline (Health: 112, General helpline: 17)."),
                sources=[], fallback_id=None, ref_no=ref, rag_backend="n/a",
            )

        # ── Service routing ──
        service = classification["service"].label
        intro = self.SERVICE_INTROS.get(service, self.SERVICE_INTROS["general"])

        # Prefer real-document RAG retrieval when it produced grounded chunks
        # (rag.py, flag RAG_BACKEND); otherwise fall back to the in-memory KB,
        # then to the "being added" placeholder for not-yet-covered services.
        if rag_result is not None and getattr(rag_result, "served", False) and rag_result.chunks:
            body = "\n\n".join(c.text for c in rag_result.chunks)
            sources = [c.source for c in rag_result.chunks]
            rag_backend = rag_result.backend
        elif service in self.SERVICES_WITH_KB:
            chunks = search_kb(user_text, service=service, top_k=2)
            if chunks:
                body = "\n\n".join(c.text for c in chunks)
                sources = [c.source for c in chunks]
            else:
                body = (f"I don't have detailed information for this exact request. "
                        f"Please visit the relevant dzongkhag office. Reference: {ref}")
                sources = []
            rag_backend = "kb"
        else:
            # New services (ndi, civil_registration, education, taxes) —
            # classifier now recognises them but KB content is Tier 2 work.
            body = (f"I have identified your request as a {service.replace('_', ' ')} "
                    f"question. Detailed information for this service is being added. "
                    f"In the meantime, please call the general helpline at 17 or visit "
                    f"www.gov.bt. Reference: {ref}")
            sources = []
            rag_backend = "kb(none)"

        bot_text = f"{intro}\n\n{body}\n\nIs there anything else I can help you with?"

        return TurnResponse(
            bot_text=bot_text, sources=sources,
            step_label="Step 3 of 4", fallback_id=None, ref_no=ref,
            rag_backend=rag_backend,
        )


# ═══════════════════════════════════════════════════════════════════
# FLASK APP
# ═══════════════════════════════════════════════════════════════════
app = Flask(__name__)


def make_classifier() -> BaseClassifier:
    if GENAI_AVAILABLE and GEMINI_API_KEY:
        try:
            classifier = GeminiClassifier(api_key=GEMINI_API_KEY)
            print(f"[startup] Using GeminiClassifier "
                  f"({classifier.model_name}, CoT, schema-constrained)")
            return classifier
        except Exception as e:
            print(f"[startup] Gemini init failed: {e}; falling back to keywords")
    else:
        print("[startup] GEMINI_API_KEY not set — falling back to KeywordClassifier. "
              "Set GEMINI_API_KEY in your environment to enable the CoT classifier.")
    return KeywordClassifier()


# ═══════════════════════════════════════════════════════════════════
# DZONGKHA TRANSLATION
#   When Team A's detector flags a Dzongkha message, we answer in
#   Dzongkha and show the English in parentheses. Translation uses the
#   Gemini model; without an API key it gracefully stays English-only.
# ═══════════════════════════════════════════════════════════════════
class GeminiTranslator:
    def __init__(self, api_key: str, model_name: str = GEMINI_MODEL_NAME):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def to_dzongkha(self, text: str) -> Optional[str]:
        prompt = (
            "Translate the following English text into Dzongkha (རྫོང་ཁ), "
            "Bhutan's national language. Preserve line breaks, bullet points, "
            "phone numbers, and reference codes exactly. Return ONLY the "
            "Dzongkha translation — no English, no transliteration, no notes.\n\n"
            f"{text}"
        )
        try:
            resp = self.model.generate_content(prompt)
            out = (resp.text or "").strip()
            return out or None
        except Exception as e:
            print(f"[translate error: {type(e).__name__}: {e}]")
            return None


def make_translator() -> Optional[GeminiTranslator]:
    if GENAI_AVAILABLE and GEMINI_API_KEY:
        try:
            print("[startup] Dzongkha translation enabled (Gemini).")
            return GeminiTranslator(api_key=GEMINI_API_KEY)
        except Exception as e:
            print(f"[startup] Translator init failed: {e}; Dzongkha replies disabled.")
    else:
        print("[startup] No API key — Dzongkha replies disabled (English only).")
    return None


# Build once on startup so the model client is reused across requests
CLASSIFIER = make_classifier()
TRANSLATOR = make_translator()
ENGINE     = ConversationEngine()

# Structured JSON logging + per-request trace_id (Team D schema). Registers
# Flask before/after_request hooks that mint/accept and echo X-Trace-ID.
obs.init_app(app)
print(f"[startup] RAG_BACKEND={RAG_BACKEND} · EMIT_CANONICAL_INTENT={EMIT_CANONICAL_INTENT} · "
      f"logging={obs.backend_name()} · team_b_rule_router={routing_adapter.TEAM_B_RULE_AVAILABLE} · "
      f"team_a_nlp_rag={rag.UPSTREAM_AVAILABLE}")


@app.route("/")
def index():
    return render_template("index.html")


def _status_for_rag(backend: str) -> str:
    if backend.startswith("docs[team_a_nlp]"):
        return "real(team_a_nlp)"
    if backend.startswith("docs"):
        return "real(vendored policy docs)"
    if backend.startswith("supabase"):
        return "stub(supabase ingest-only)"
    if backend.startswith("kb"):
        return "fallback(in-memory KB)"
    return backend


def _status_for_route(backend: str) -> str:
    if backend.startswith("agent[team_b]"):
        return "real(Team B LangGraph agent)"
    if backend.startswith("rule[team_b]"):
        return "real(Team B rule router)"
    return "fallback(inline regex copy)"


def run_pipeline(user_text: str, trace_id: str, asr_meta: Optional[Dict] = None) -> Dict:
    """The full per-turn pipeline, shared by /api/chat and /api/voice.

    classify → enrich → RAG → route → canonical-intent → (Dzongkha) → respond,
    with trace_id carried through every stage and a `pipeline` report describing
    which real component (vs. fallback/stub) handled each stage.
    """
    t0 = time.time()
    obs.log_event("INFO", "chat.received",
                  f"input received via {'voice' if asr_meta else 'text'}",
                  trace_id, chars=len(user_text), via="voice" if asr_meta else "text")

    # 1) classify (Gemini CoT, or keyword fallback with no key)
    classification = CLASSIFIER.classify(user_text)
    classifier_kind = type(CLASSIFIER).__name__

    # 2) enrich — Team A NLP: language detect + entity extraction
    enrichment = enrich(user_text)
    language = enrichment["language"]
    entities = enrichment["entities"]

    # 3) RAG retrieval (flag RAG_BACKEND); KB fallback handled in the engine
    service = classification["service"].label
    rag_result = None
    if RAG_BACKEND != "kb":
        try:
            rag_result = rag.retrieve(user_text, service=service, language=language)
        except Exception as exc:
            obs.log_event("WARN", "rag.error", f"RAG failed: {type(exc).__name__}", trace_id)

    response = ENGINE.process(user_text, classification, rag_result=rag_result)

    # 4) routing — real Team B router/agent if available, else inline fallback
    route_res = routing_adapter.route(user_text, trace_id)
    routing = route_res.routing

    # 5) canonical intent schema (Team D) — map 4 dims → v2 + validate
    canonical = None
    schema_status: Dict = {"emitted": False}
    if EMIT_CANONICAL_INTENT:
        canonical = intent_schema.to_canonical_payload(
            user_text=user_text, language=language, classification=classification,
            classifier_kind=classifier_kind, entities=entities, routing=routing,
            trace_id=trace_id, latency_ms=int((time.time() - t0) * 1000),
        )
        ok_ext, _ = intent_schema.validate(canonical)
        ok_strict, err_strict = intent_schema.validate(canonical, strict_canonical=True)
        schema_status = {
            "emitted": True,
            "canonical_intent": canonical["classification"]["intent"],
            "extended_valid": ok_ext,
            "strict_canonical_valid": ok_strict,
            "strict_canonical_note": err_strict,
        }

    obs.log_event("INFO", "route.decided",
                  f"routed to {routing.get('agent')} via {route_res.backend}", trace_id,
                  intent=routing.get("intent"), agent=routing.get("agent"),
                  rag_backend=response.rag_backend, routing_backend=route_res.backend)

    # 6) Dzongkha reply (Gemini translation; English-only without a key)
    bot_text = response.bot_text
    translated = False
    if language == "dz" and TRANSLATOR is not None:
        dzongkha = TRANSLATOR.to_dzongkha(bot_text)
        if dzongkha:
            bot_text = f"{dzongkha}\n\n({bot_text})"
            translated = True

    pipeline = {
        "trace_id": trace_id,
        "classify": {"component": classifier_kind,
                     "status": "real(Gemini CoT)" if classifier_kind == "GeminiClassifier"
                               else "fallback(keyword)"},
        "enrich":   {"component": "nlp_enrichment (Team A NLP)", "status": "real"},
        "rag":      {"component": response.rag_backend,
                     "status": _status_for_rag(response.rag_backend),
                     "detail": getattr(rag_result, "detail", "") if rag_result else "RAG_BACKEND=kb"},
        "route":    {"component": route_res.backend, "status": _status_for_route(route_res.backend),
                     "detail": route_res.detail},
        "schema":   {"component": "nlp_intent_schema_v2 (Team D)", **schema_status},
        "translate": {"component": "GeminiTranslator", "applied": translated,
                      "status": "real" if translated else ("off(no key)" if TRANSLATOR is None else "n/a")},
        "logging":  {"component": obs.backend_name(),
                     "status": "real(Team D)" if obs.TEAM_D_LOGGING_AVAILABLE
                               else "fallback(team-d schema)"},
    }
    if asr_meta:
        pipeline["asr"] = {"component": "asr_adapter (Team C contract)",
                           "status": "client" if asr_meta.get("source") == "client"
                                     else "stub(fixture)",
                           "confidence": asr_meta.get("confidence"),
                           "language": asr_meta.get("language")}

    obs.log_event("INFO", "chat.completed", "turn complete", trace_id,
                  latency_ms=int((time.time() - t0) * 1000), service=service,
                  language=language, classifier=classifier_kind)

    result = {
        "bot_text":    bot_text,
        "sources":     response.sources,
        "step_label":  response.step_label,
        "fallback_id": response.fallback_id,
        "ref_no":      response.ref_no,
        "classification": {
            k: {"label": v.label, "confidence": v.confidence}
            for k, v in classification.items()
        },
        "language":    language,
        "entities":    entities,
        "routing":     routing,
        "classifier_kind": classifier_kind,
        "trace_id":    trace_id,
        "pipeline":    pipeline,
        "canonical_intent": canonical,
    }
    if asr_meta:
        result["asr"] = asr_meta
    return result


@app.route("/api/chat", methods=["POST"])
def chat():
    payload   = request.get_json(silent=True) or {}
    user_text = (payload.get("message") or "").strip()
    if not user_text:
        return jsonify({"error": "empty message"}), 400
    return jsonify(run_pipeline(user_text, g.trace_id))


@app.route("/api/voice", methods=["POST"])
def voice():
    """Team C voice-input entry point: accepts a transcription (text + confidence
    + language) OR a named fixture_id, then drives the SAME pipeline as /api/chat."""
    payload = request.get_json(silent=True) or {}
    try:
        asr = asr_adapter.transcribe(
            transcript=payload.get("transcript"),
            confidence=payload.get("confidence"),
            language=payload.get("language"),
            fixture_id=payload.get("fixture_id"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "fixtures": asr_adapter.list_fixtures()}), 400
    obs.log_event("INFO", "asr.transcribed", "voice input resolved", g.trace_id,
                  source=asr.source, confidence=asr.confidence, language=asr.language)
    return jsonify(run_pipeline(asr.transcript, g.trace_id, asr_meta=asr.to_dict()))


@app.route("/healthz")
def healthz():
    return {
        "ok": True,
        "classifier": type(CLASSIFIER).__name__,
        "flags": {
            "RAG_BACKEND": RAG_BACKEND,
            "EMIT_CANONICAL_INTENT": EMIT_CANONICAL_INTENT,
            "USE_TEAM_B_AGENT": os.environ.get("USE_TEAM_B_AGENT", "0"),
        },
        "backends": {
            "logging": obs.backend_name(),
            "team_b_rule_router": routing_adapter.TEAM_B_RULE_AVAILABLE,
            "team_a_nlp_rag": rag.UPSTREAM_AVAILABLE,
        },
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
