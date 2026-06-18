# Bhutan Public Services Assistant

Voice-first AI assistant for Bhutan public services, built by Team A.

- **Backend**: Flask + Gemini classifier + conversation engine + knowledge base
- **Frontend**: Single-page chat UI styled to match the Omdena visual brand
- **Dev mode**: Toggle in the header reveals per-message classification (in-scope / safety / request type / service) with confidence scores
- **NLP enrichment**: Bilingual (English / Dzongkha) language detection + structured entity extraction (CID, plot ID, tax year, document type) — see Credits

---

## Credits — cross-team integration

Each `/api/chat` response is built from three teams' work, all dependency-free
(regex only — nothing added to `requirements.txt`) and shown in Dev Mode:

- **Team A NLP track** (`team_a_nlp/`) → [`nlp_enrichment.py`](nlp_enrichment.py):
  bilingual `IntentClassifier` — Dzongkha Unicode detection + entity extraction
  (CID, plot ID, tax year, document type). Their Ollama + Supabase pgvector RAG
  ingestion pipeline is the Tier-2 vector-DB retrieval path on the roadmap.
- **Team B routing module** (`team_b/routing_module/`) → [`team_b_routing.py`](team_b_routing.py):
  the deterministic `IntentRouter` — maps a request to the downstream agent
  (`permit_agent`, `business_reg_agent`, …) and extracts routing slots
  (district, facility, document type, agency).

When a citizen writes in Dzongkha, the assistant replies in Dzongkha with the
English translation in parentheses (Gemini-powered; English-only without a key).

---

## Run locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) set your Gemini key to enable the CoT classifier + Dzongkha replies.
#    Never hardcode it — the app.py default is "" and falls back to the keyword
#    classifier so it runs key-free. Use a gitignored .env / shell export.
export GEMINI_API_KEY="your-key-here"

# 3. Run
python app.py
```

Open http://localhost:5000

If `GEMINI_API_KEY` is missing or the Gemini library isn't installed, the app automatically falls back to the keyword classifier — the UI still works.

---

## Deploy to Render (free, ~10 minutes)

Render gives you a public HTTPS URL you can paste in Slack and share with your team lead.

### Step 1 — Put the code on GitHub

```bash
cd bhutan-assistant
git init
git add .
git commit -m "Initial commit"
```

Create a new repo on github.com (call it `bhutan-assistant`), then:

```bash
git remote add origin https://github.com/<your-username>/bhutan-assistant.git
git branch -M main
git push -u origin main
```

> ⚠️ **Before pushing**, open `app.py` and replace the hardcoded `GEMINI_API_KEY` default with `""`. Pushing a real key to a public repo will get it revoked automatically by Google.

### Step 2 — Connect Render

1. Go to https://render.com and sign in with GitHub.
2. Click **New +** → **Web Service**.
3. Pick your `bhutan-assistant` repo.
4. Render auto-detects `render.yaml`. Confirm the settings:
   - Runtime: `Python`
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Plan: **Free**
5. Under **Environment**, add:
   - `GEMINI_API_KEY` = your real Gemini key
6. Click **Create Web Service**.

Render builds and deploys. After ~3–5 minutes you'll see a URL like:

```
https://bhutan-assistant.onrender.com
```

That's the link to send to your team lead.

> 📝 The free plan sleeps after 15 min of inactivity and wakes up on the next request (~30 sec cold start). Fine for a demo.

### Step 3 — Share with team lead

Drop this in Slack / email:

> Hi [lead] — here's the prototype with Gemini classifier + dev-mode toggle:
> 🔗 https://bhutan-assistant.onrender.com
> Flip the "Dev mode" switch in the top right to see the classifier output on every message.

---

## Alternative: Deploy to Railway

Same idea: connect GitHub repo, add `GEMINI_API_KEY` env var, deploy. Railway auto-detects the `Procfile`.

## Alternative: Deploy to Fly.io / Hugging Face Spaces

- **Fly.io**: `fly launch` then `fly deploy` — set the key with `fly secrets set GEMINI_API_KEY=…`.
- **HF Spaces**: create a new Space (Gradio template), but you'd need to refactor to a Gradio app. Render is easier for this Flask setup.

---

## File structure

```
bhutan-assistant/
├── app.py                # Flask backend: classifier + engine + /api/chat, /api/voice
├── nlp_enrichment.py     # language detect + entities (Team A NLP, vendored)
├── team_b_routing.py     # inline regex router (Team B routing_module, vendored fallback)
├── rag.py                # RAG retrieval (policy docs / supabase-stub / kb), flag-controlled
├── intent_schema.py      # 4-dim → canonical nlp_intent_schema_v2 (Team D) + validation
├── routing_adapter.py    # real Team B router / LangGraph agent, with fallback
├── asr_adapter.py        # Team C voice-input adapter (+ asr_fixtures.json)
├── obs.py                # structured JSON logging + trace_id (Team D schema)
├── policy_docs/          # vendored bilingual EN/DZ policy docs (RAG source; from shared/)
├── schemas/              # canonical + prototype-extended nlp_intent_schema_v2
├── reports/              # reproducible classifier benchmark + vendored test set
├── tests/                # 43 unit + e2e tests
├── templates/index.html  # Frontend (Omdena-styled chat UI + dev-mode pipeline inspector)
├── MODULES.md            # per-module reference (purpose / I/O / limitations / provenance)
├── requirements.txt · Procfile · render.yaml · .gitignore · README.md
```

---

## Integration layer (Phase 3)

This prototype now integrates the other teams' real components behind feature
flags, with safe fallbacks so it stays deployable on the Render free tier with
**zero API keys**. Full details in [MODULES.md](MODULES.md) and
[../INTEGRATION_PLAN.md](../INTEGRATION_PLAN.md). Each `/api/chat` response now
reports, per stage, which component handled it (`real` / `fallback` / `stub`),
and a `trace_id` is carried end-to-end and echoed via the `X-Trace-ID` header.

| Flag (env var) | Default | Effect |
|---|---|---|
| `RAG_BACKEND` | `kb` | `kb` (in-memory) · `docs` (real bilingual policy docs, Team A NLP approach) · `supabase` (pgvector stub → docs/kb) |
| `USE_TEAM_B_AGENT` | `0` | `1` + `GROQ_API_KEY` ⇒ Team B LangGraph agent; else the rule router |
| `EMIT_CANONICAL_INTENT` | `1` | emit + validate the canonical `nlp_intent_schema_v2` payload (Team D) |

### What is real vs. stubbed

| Stage | Real when… | Otherwise |
|---|---|---|
| Classify | `GEMINI_API_KEY` set (Gemini CoT) | keyword fallback (offline) |
| Enrich (lang + entities) | always (Team A NLP logic, vendored) | — |
| RAG | `RAG_BACKEND=docs` → real policy-doc retrieval | `kb` in-memory fallback |
| Route | Team B `routing_module` present (monorepo) / LangGraph agent w/ key | inline regex copy |
| Canonical intent | always emitted + validated (extended schema) | strict canonical v2 diverges by design |
| Voice (ASR) | client-supplied transcript | canned fixture (Team C scripts not importable) |
| Logging | Team D `service_logging` present | field-identical local fallback |

## API

### `POST /api/chat`

```json
{ "message": "What documents do I need for a construction permit?" }
```

Response (abridged — keys preserved for UI back-compat, plus the Phase-3 additions):

```json
{
  "bot_text": "Great! Let me guide you through that…",
  "sources": ["land_policy.txt"],
  "step_label": "Step 3 of 4",
  "fallback_id": null,
  "ref_no": "REF-A1B2C3D4",
  "classification": {
    "in_scope":     { "label": "in_scope",         "confidence": 0.97 },
    "safety":       { "label": "safe",             "confidence": 0.99 },
    "request_type": { "label": "document_inquiry", "confidence": 0.94 },
    "service":      { "label": "permits",          "confidence": 0.98 }
  },
  "language": "en",
  "entities": { "tax_year": "2026" },
  "routing": { "agent": "permit_agent", "intent": "permit_support", "confidence": 0.7, "slots": {} },
  "classifier_kind": "KeywordClassifier",
  "trace_id": "TRC-9FF0EEE5",
  "pipeline": { "classify": {"component": "...", "status": "real|fallback|stub"}, "...": "per-stage report" },
  "canonical_intent": { "request_id": "…", "classification": { "intent": "INFO", "...": "…" }, "...": "nlp_intent_schema_v2" }
}
```

### `POST /api/voice`

Drives the **same** pipeline from voice. Send a client transcription or a fixture id:

```json
{ "transcript": "How do I register my child's birth?", "confidence": 0.9, "language": "en" }
{ "fixture_id": "dz_tax_2026" }
```

### `GET /healthz`

Returns the active flags + which real backends were detected.

## Tests

```bash
.venv/Scripts/python -m pytest    # 43 unit + e2e tests (no key/network needed)
```
