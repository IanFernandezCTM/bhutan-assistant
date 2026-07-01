# Team A — Prototype (THE PRODUCT)

*The "actually works and is live on the internet" team.*

---

## The 30-second version (say this out loud)

> "The prototype is the real, deployable product — the thing citizens would actually
> use. It's a web app: a citizen speaks or types a question, the system looks up the
> answer in Bhutan's official policy documents, and answers back — in the citizen's
> language, out loud. The clever part is how it does this cheaply and safely: it makes
> **one** call to a large language model per question, and that single call is
> instructed to answer *only* from the official documents, quote numbers exactly, and
> say 'I don't know, here's the office to call' when it isn't sure. It's designed so
> the AI brain can start on a rented cloud server today and move to the government's
> own computer later by changing a single setting — no rewrite."

That's the whole product. Everything below is detail.

---

## Why this is "the product"

The other teams built pieces — voice, language understanding, an agent, logging. The
prototype is the one place where a real citizen can go to a web page and get help.
It started as a demo and became the chosen path forward because it produces better,
safer answers, is cheap to run, and is built to run on hardware the government owns.

Two big ideas define it:

1. **LLM-first.** Instead of a long chain of separate steps (classify the question,
   then look up a template, then translate…), it hands the heavy lifting to *one*
   smart language-model call. That call figures out the answer, the topic, the
   safety check, and the language all at once.
2. **Grounded and honest.** The AI is only allowed to answer from official documents
   it's shown. If the documents don't contain the answer, it **abstains** — it
   refuses to guess. For a government service, a confident wrong answer is worse than
   "I don't have that; please call this office."

---

## What they built (in plain English)

The app is a set of small, focused Python files. Here's each one, plainly:

| File | What it does, in one sentence |
|---|---|
| `app.py` | The web server — receives questions, runs the pipeline, sends back answers. The "front desk." |
| `llm.py` | The connection to the AI brain. **The single most important file for the government's goal.** |
| `assistant.py` | The instructions given to the AI: "answer only from these documents, quote numbers exactly, refuse if unsure." |
| `rag.py` | The document search — finds the right policy passages to show the AI. |
| `nlp_enrichment.py` | Detects the language and pulls out ID numbers (borrowed from Team A NLP). |
| `translate.py` | Turns English answers into Dzongkha, protecting numbers so they never get mangled. |
| `tts_dz.py` | Speaks the Dzongkha answer out loud. |
| `routing_adapter.py`, `intent_schema.py`, `obs.py`, `asr_adapter.py` | The "adapters" that plug in the other teams' work (routing, the shared schema, logging, voice input). |
| `templates/index.html` | The web page itself — styled to look like an official GovTech Bhutan service, big microphone button, plays answers aloud. |

### The "swap point" — the most important thing to understand
**File:** `llm.py`

The app talks to the AI through **three settings**:

- `LLM_BASE_URL` — *where* the AI lives (a web address)
- `LLM_API_KEY` — the password to use it
- `LLM_MODEL` — *which* AI model to use

Today those point to a rented cloud service (**DeepInfra**) running an open model
called **Qwen3-32B**. Tomorrow, to run on the government's own GPU, you change
`LLM_BASE_URL` to point at that machine — **and nothing else changes.** Same model,
same behavior.

> **Say it like this:** "The AI brain is plugged in through a standard socket. Right
> now it's plugged into a rented cloud outlet. To make it fully sovereign — running on
> Bhutan's own hardware — you just move the plug to the local outlet. One setting.
> That's the whole point of the design."

Why "open model"? Because Qwen3-32B's "weights" (the actual AI) can be downloaded and
run on your own computer. A closed model like GPT or Gemini can only be rented — you
could never move it onto a government machine. Choosing an open model is what makes
the "own it later" promise real.

---

## How a question flows through it (step by step)

```
Citizen asks a question (voice or text)
      │
      ▼
1. ENRICH      → What language? Any ID numbers? (fast, rule-based, no AI)
      │
      ▼
2. RETRIEVE    → Search the policy docs, grab the most relevant passages
      │           (English + the matching Dzongkha version, side by side)
      ▼
3. ONE AI CALL → "Here are the official passages. Answer the question using ONLY these.
      │           Quote numbers exactly. If they don't answer it, say so. Also tell me
      │           the topic, whether it's in scope, and whether it's safe."
      │           ← the answer, topic, safety, and confidence all come back together
      ▼
4. TRANSLATE   → If the citizen used Dzongkha, translate the answer (numbers protected)
      │
      ▼
5. SPEAK       → Play the answer out loud
      │
      ▼
   Answer delivered — plus a hidden "operator panel" showing exactly what each step did
```

For an English question that's **one AI call**. For Dzongkha it's **two** (answer +
translate). Compare that to other approaches that make four or more calls per
question — this is why the prototype is faster and cheaper.

---

## The Dzongkha strategy (why it's smarter than it looks)

Here's a subtle, important decision. Research shows that today's AI models are **bad
at *writing* Dzongkha** — they make up words and mangle numbers. So the prototype
**never lets the AI freely write Dzongkha facts.** Instead:

- The official documents are already **bilingual** — every English section has a
  matching, human-written Dzongkha section.
- When answering in Dzongkha, the system leans on that **human-written** text and
  copies numbers **character-for-character**.

> **Say it like this:** "We don't ask the AI to *translate the law* — it fails at that.
> We ask it to *pick the right official passage* that a human already wrote. That turns
> an impossible job into an easy one, and it's why the answers can be trusted."

---

## The safety net (so it never crashes)

The app is built to **degrade gracefully**. If the AI connection isn't configured, it
falls back to a simple offline keyword system so the app still boots and answers. If
the AI call fails mid-request, it catches the error and uses the fallback instead of
showing an error page. This is why it's safe to deploy.

---

## Where it lives right now

- **Live on Google Cloud Run** (Mumbai region, closest to Bhutan).
- The AI runs on **DeepInfra / Qwen3-32B** today.
- It **scales to zero** when idle — costs almost nothing when nobody's using it.
- The password (API key) is stored safely in Google's Secret Manager, never in the code.

**Important honesty note:** because the cloud AI is off-premises, only **fake/public
test questions** should be used on the live demo. **Real citizen data must wait** until
the AI is moved onto the government's own machine.

---

## What's genuinely good

- **It works and it's live.** Real, deployable, running today.
- **One AI call per question** → fast, cheap, and scales easily to thousands of
  conversations a day.
- **Grounded + abstaining** → it refuses to make up answers, which is the single most
  important property for a government service.
- **Tiny footprint** — it doesn't need heavy AI libraries in the web layer, so it's
  cheap to host and simple to maintain.
- **Sovereign-ready by design** — open model + one-setting swap to local hardware.

## What to be honest about

- The famous **"95.1% accuracy"** number written in the code is from an *old* version
  and is **unverified** — don't quote it. (See `PROVENANCE_AUDIT.md`.)
- There's **no end-to-end answer-quality test yet.** The design is sound, but proving
  it needs a proper evaluation set (200–500 real questions) — that's the top of the
  to-do list.
- The **document search is still basic** (word-matching, like the NLP team's). The
  planned upgrade is "meaning-based" search (embeddings) for better recall.
- **Dzongkha voice** quality still depends on either machine translation or
  pre-recorded audio — a real open question flagged in the plan.

---

## The one thing to remember

> **The prototype is the live, working product built around a single idea: one honest,
> grounded AI call per question, plugged in through a socket that can move from rented
> cloud today to the government's own GPU tomorrow — without a rewrite.**

---

## Words you can drop to sound like you know it

- **LLM-first** — let one smart AI call do the work instead of many small steps.
- **Grounding** — answer only from real documents you're shown.
- **Abstention** — refusing to answer when the documents don't cover it (a feature, not a bug).
- **Open weights** — an AI model you can download and run on your own hardware (Qwen3-32B).
- **OpenAI-compatible endpoint** — the standard "socket" the app plugs the AI into.
- **vLLM** — the software that will run the open model on the government's GPU later.
- **Data sovereignty** — keeping citizen data on hardware the government owns and controls.
- **Scales to zero** — costs nothing when idle.
