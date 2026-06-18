# Integration modules (Phase 3)

Per-module reference for the cross-team integration layer added in
`team-a/integration-sweep`. Every module prefers a **real** team component when
present and falls back safely, so the app boots and answers with **zero API keys**
on the Render free tier. Each stage reports `real` / `fallback` / `stub` honestly
in the dev-mode UI and structured logs.

Design pattern (all modules): **vendor what must run in prod · guarded/lazy import
of the real sibling package when present (monorepo) · feature flag · safe fallback.**
On the Render deploy repo only `team_a_prototype/`'s contents exist, so sibling
imports (`team_a_nlp`, `team_b`, `team_d_integrations`) fail there and the vendored
path is used.

| Flag (env var) | Default | Meaning |
|---|---|---|
| `RAG_BACKEND` | `kb` | `kb` \| `docs` \| `supabase` |
| `USE_TEAM_B_AGENT` | `0` | `1` + `GROQ_API_KEY` ⇒ try Team B's LangGraph agent |
| `EMIT_CANONICAL_INTENT` | `1` | emit + validate the canonical intent payload |
| `GEMINI_API_KEY` | (unset) | enables Gemini classifier + Dzongkha translation |

---

### `rag.py` — RAG retrieval
- **Purpose:** retrieve grounding chunks for the answer; replaces the hardcoded KB when enabled.
- **In/out:** `retrieve(query, service, language, top_k=2, backend=None) -> RagResult{chunks, backend, served, detail}`.
- **Backends:** `docs` = term-frequency over vendored `policy_docs/*.txt` (real); `supabase` = best-effort pgvector (**stub** — Team A NLP ingest has no retrieval path; degrades to docs→kb); `kb` = defer to in-memory KB.
- **Provenance:** scoring/chunking reuse `team_a_nlp/rag_pipeline.py` (Team A NLP, credited); docs vendored from `shared/policy_docs` (bilingual EN/DZ).
- **Limitations:** the corpus covers land/tax/civil/constitution — **no permit/health/business doc**, so `kb` (curated) gives better answers for those; `docs` shines for land/tax/civil queries. Term-frequency, not embeddings.

### `intent_schema.py` — canonical intent reconciliation
- **Purpose:** map the prototype's 4 dimensions → Team D's canonical `nlp_intent_schema_v2` (single intent ∈ INFO/NAV/TRANS/CLARIF/ESCL + 5-way scores), and validate.
- **In/out:** `to_canonical_payload(...) -> dict`; `validate(payload, strict_canonical=False) -> (ok, err)`; `map_to_canonical_intent(classification) -> (intent, conf, basis)`.
- **Provenance/target:** Team D `test_nlp_intent_schema/nlp_intent_schema_v2.json`. Validated against a vendored **extended** copy (`schemas/nlp_intent_schema_v2.prototype.json`) that adds a `PROTOTYPE` model_family + Gemini/keyword model_ids + an `extensions` block.
- **Limitations:** `scores` is a **documented shim** (synthesized from one confidence, not a real softmax). The payload **fails strict canonical v2** (additive `extensions`/model_id) — see [CROSS_TEAM_NOTES.md](../CROSS_TEAM_NOTES.md) for the upstream enum-widening PR.

### `routing_adapter.py` — routing
- **Purpose:** route a request to a downstream agent, preferring real Team B components.
- **In/out:** `route(text, trace_id) -> RouteResult{routing, backend, detail, agent_response}`. `routing` keeps the UI shape `{agent, intent, confidence, slots, ...}`.
- **Backends:** `agent[team_b]` = Team B `pipeline.TeamBPipeline` (LangGraph/Groq, **gated by `USE_TEAM_B_AGENT` + `GROQ_API_KEY`**, lazy-imported to avoid an import-time Groq crash); `rule[team_b]` = Team B `routing_module.intent_router` (real, offline); `rule[inline]` = the vendored `team_b_routing.py` (always-available fallback).
- **Provenance:** `team_b/routing_module/` (Team B). The inline copy is a faithful copy minus logging.
- **Limitations:** the LangGraph path needs a key + heavy deps (not on free tier); the agent tools are canned stubs upstream.

### `asr_adapter.py` — voice input (Team C)
- **Purpose:** accept a transcription (text + confidence + language) so voice drives the same pipeline.
- **In/out:** `transcribe(transcript=None, confidence=None, language=None, fixture_id=None) -> AsrResult`. Exposed at `POST /api/voice`.
- **Provenance:** Team C `team_c_voice/` (Whisper + Silero VAD).
- **Limitations:** Team C's scripts aren't importable (load models + REPL at import, no confidence), so real in-process ASR is **not wired** — input is client-supplied or a canned fixture (`asr_fixtures.json`). See [CROSS_TEAM_NOTES.md](../CROSS_TEAM_NOTES.md).

### `obs.py` — structured logging + trace_id
- **Purpose:** one `trace_id` per request, carried end-to-end, with structured JSON logs in Team D's schema.
- **In/out:** `log_event(level, event, message, trace_id=None, **metadata) -> dict`; `init_app(flask_app)` registers before/after_request (mint/accept + echo `X-Trace-ID`). `LogEntry` fields: `timestamp·level·trace_id·service·event·message·metadata`.
- **Provenance:** Team D `service_logging` (delegates to its `log_json`/`generate_trace_id` when importable + pydantic present; otherwise a field-identical local fallback — the path that ships).
- **Limitations:** Team D's middleware is FastAPI-only, so the Flask shim lives here; trace format `TRC-XXXXXXXX` (inbound UUIDs also accepted).

---

## Run

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest                      # 43 tests
RAG_BACKEND=docs .venv/Scripts/python app.py        # real-doc RAG on; open http://localhost:5000
.venv/Scripts/python reports/benchmark_classifier.py
```
