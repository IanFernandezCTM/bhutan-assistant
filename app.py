"""
═══════════════════════════════════════════════════════════════════════
  BHUTAN VOICE-FIRST PUBLIC SERVICE ASSISTANT — Flask Backend
  Wraps the Team 4 classifier + conversation engine in a web API.
═══════════════════════════════════════════════════════════════════════
"""

import os
import json
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from flask import Flask, request, jsonify, render_template

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════
# CONFIG — read from environment variable (safer than hardcoding)
# Fall back to the hardcoded key only for local dev convenience.
# ═══════════════════════════════════════════════════════════════════
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""  # ← replace before deploy
)
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")


# ═══════════════════════════════════════════════════════════════════
# CLASSIFIER PROMPT
# ═══════════════════════════════════════════════════════════════════
CLASSIFIER_PROMPT_TEMPLATE = """You are a request classifier for a Bhutan public-service voice assistant. \
Classify the user's request along 4 dimensions and return a JSON object.

USER REQUEST: "{user_text}"

DIMENSIONS

1) in_scope — is this about Bhutanese public services?
   • "in_scope"     — permits, health services, business registration, NDI,
                      civil registration, taxes, education, etc.
   • "out_of_scope" — sports, entertainment, weather, jokes, stock prices,
                      general chat, anything else.

2) safety — is this safe to answer with general/procedural information?
   • "safe"   — information, navigation, document checklists, office locations.
   • "unsafe" — requests for medical diagnosis, treatment, prescriptions,
                or specific legal/financial advice.

3) request_type — what kind of help is the user asking for? Pick ONE from:
   {request_types}

4) service — which government domain does this belong to? Pick ONE from:
   {services}

OUTPUT FORMAT — return ONLY this JSON object, nothing else:
{{
  "in_scope":     {{"label": "...", "confidence": 0.0}},
  "safety":       {{"label": "...", "confidence": 0.0}},
  "request_type": {{"label": "...", "confidence": 0.0}},
  "service":      {{"label": "...", "confidence": 0.0}}
}}

Confidence is a number between 0.0 and 1.0 expressing how sure you are."""


REQUEST_TYPES = [
    "document_inquiry", "status_check", "office_location",
    "application_start", "eligibility_check", "general_info", "other",
]

SERVICES = ["permits", "health", "business", "general"]


# ═══════════════════════════════════════════════════════════════════
# CLASSIFIERS
# ═══════════════════════════════════════════════════════════════════
@dataclass
class ClassificationResult:
    label: str
    confidence: float


class BaseClassifier:
    def classify(self, user_text: str) -> Dict[str, ClassificationResult]:
        raise NotImplementedError


class GeminiClassifier(BaseClassifier):
    def __init__(self, api_key: str, model_name: str = GEMINI_MODEL_NAME):
        if not GENAI_AVAILABLE:
            raise ImportError("google-generativeai not installed.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name,
            generation_config={"response_mime_type": "application/json"},
        )

    def classify(self, user_text: str) -> Dict[str, ClassificationResult]:
        prompt = CLASSIFIER_PROMPT_TEMPLATE.format(
            user_text=user_text.replace('"', "'"),
            request_types=", ".join(REQUEST_TYPES),
            services=", ".join(SERVICES),
        )
        try:
            response = self.model.generate_content(prompt)
            data = json.loads(response.text)
            return self._parse(data)
        except Exception as e:
            print(f"[classifier error: {type(e).__name__}: {e}]")
            return self._unknown()

    def _parse(self, data: Dict) -> Dict[str, ClassificationResult]:
        out = {}
        for key in ("in_scope", "safety", "request_type", "service"):
            entry = data.get(key, {})
            if not isinstance(entry, dict):
                entry = {}
            out[key] = ClassificationResult(
                label=str(entry.get("label", "unknown")),
                confidence=float(entry.get("confidence", 0.0)),
            )
        return out

    @staticmethod
    def _unknown() -> Dict[str, ClassificationResult]:
        return {k: ClassificationResult("unknown", 0.0)
                for k in ("in_scope", "safety", "request_type", "service")}


class KeywordClassifier(BaseClassifier):
    OUT_OF_SCOPE_WORDS = [
        "cricket", "football", "soccer", "movie", "joke", "weather",
        "stock", "forex", "election", "recipe", "song", "celebrity",
    ]
    UNSAFE_WORDS = [
        "diagnose", "diagnosis", "cancer", "tumour", "tumor",
        "treatment", "prescription", "should i take",
        "what disease", "am i sick", "do i have",
    ]
    SERVICE_KEYWORDS = {
        "permits":  ["permit", "license", "licence", "construction",
                     "timber", "stone", "sand"],
        "health":   ["hospital", "doctor", "clinic", "bhu", "vaccin",
                     "medic", "health", "sick", "pain"],
        "business": ["business", "register", "registration", "company",
                     "proprietor", "trade"],
    }
    TYPE_KEYWORDS = {
        "document_inquiry":  ["document", "papers", "what do i need",
                              "checklist", "requirement"],
        "status_check":      ["status", "track", "reference",
                              "where is my", "progress"],
        "office_location":   ["office", "where", "address", "location",
                              "directions"],
        "application_start": ["apply", "start", "submit", "register",
                              "begin", "new"],
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

    def _in_scope(self, t: str) -> ClassificationResult:
        if any(w in t for w in self.OUT_OF_SCOPE_WORDS):
            return ClassificationResult("out_of_scope", 0.8)
        return ClassificationResult("in_scope", 0.7)

    def _safety(self, t: str) -> ClassificationResult:
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
# KNOWLEDGE BASE
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
        score = sum(1 for kw in c.keywords if kw in t)
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


class ConversationEngine:
    SERVICE_INTROS = {
        "permits":  "Great! Let me guide you through that.",
        "health":   "Of course! Let me guide you to the right information.",
        "business": "Great! Let me guide you through the process.",
        "general":  "Let me share what I can help with.",
    }

    def process(self, user_text, classification):
        ref = f"REF-{uuid.uuid4().hex[:8].upper()}"

        if classification["in_scope"].label == "out_of_scope":
            return TurnResponse(
                bot_text=("I can help only with the public services in this assistant. "
                          "I can still help you find the right office, start again, "
                          "or talk to a person."),
                sources=[], fallback_id="FB-03", ref_no=ref,
            )

        if classification["safety"].label == "unsafe":
            return TurnResponse(
                bot_text=("I can share general health information, but I'm not able to "
                          "give medical advice or diagnose conditions. "
                          "For personal health guidance, please visit your nearest BHU "
                          "or call 112."),
                sources=[], fallback_id=None, ref_no=ref,
            )

        service = classification["service"].label
        if service not in {"permits", "health", "business"}:
            service = "general"

        chunks = search_kb(user_text, service=service, top_k=2)
        intro = self.SERVICE_INTROS.get(service, self.SERVICE_INTROS["general"])

        if chunks:
            body = "\n\n".join(c.text for c in chunks)
            sources = [c.source for c in chunks]
        else:
            body = (f"Please visit the relevant dzongkhag office for specific "
                    f"details. Your reference: {ref}")
            sources = []

        bot_text = f"{intro}\n\n{body}\n\nIs there anything else I can help you with?"

        return TurnResponse(
            bot_text=bot_text, sources=sources,
            step_label="Step 3 of 4", fallback_id=None, ref_no=ref,
        )


# ═══════════════════════════════════════════════════════════════════
# FLASK APP
# ═══════════════════════════════════════════════════════════════════
app = Flask(__name__)


def make_classifier() -> BaseClassifier:
    if GENAI_AVAILABLE and GEMINI_API_KEY and "PASTE" not in GEMINI_API_KEY:
        try:
            return GeminiClassifier(api_key=GEMINI_API_KEY)
        except Exception as e:
            print(f"[Gemini init failed: {e}; falling back to keywords]")
    return KeywordClassifier()


# Build once on startup so the model client is reused across requests
CLASSIFIER = make_classifier()
ENGINE = ConversationEngine()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_text = (payload.get("message") or "").strip()
    if not user_text:
        return jsonify({"error": "empty message"}), 400

    classification = CLASSIFIER.classify(user_text)
    response = ENGINE.process(user_text, classification)

    return jsonify({
        "bot_text": response.bot_text,
        "sources": response.sources,
        "step_label": response.step_label,
        "fallback_id": response.fallback_id,
        "ref_no": response.ref_no,
        "classification": {
            k: {"label": v.label, "confidence": v.confidence}
            for k, v in classification.items()
        },
        "classifier_kind": type(CLASSIFIER).__name__,
    })


@app.route("/healthz")
def healthz():
    return {"ok": True, "classifier": type(CLASSIFIER).__name__}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
