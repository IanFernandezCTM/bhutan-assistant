# Team B — Agentic Workflow & Contracts

*The "smart agent that takes action" team.*

---

## The 30-second version (say this out loud)

> "Team B built the most elaborate version of the assistant — a full multi-step 'agent'
> that listens, checks the request for safety, figures out the topic, and then uses
> *tools* to actually look things up, like a business's tax status or a land record by
> its plot number. It's built as a 13-step pipeline using a framework called LangGraph.
> It's genuinely the best of any team at *transactions* — doing something on the
> citizen's behalf — and it has the project's only real, labelled test set. Its
> weaknesses: it makes four or more AI calls per question so it's slow (20–40 seconds),
> and its AI brain runs on a rented service called Groq that you *can't* move onto the
> government's own hardware."

That's Team B. Details below.

---

## Why this team exists

Some citizen requests aren't just "tell me about X." They're "check *my* application,"
"look up *my* land record," "is *my* business tax-compliant?" Answering those means
the system has to **take an action** — call a database, fetch a specific record, and
respond with real data. That's what an **agent** does: it doesn't just talk, it acts.

Team B built the "action-taking" brain of the project.

---

## What they built (in plain English)

Team B's folder is the biggest and richest in the repo. Here are the main pieces:

### 1. The LangGraph agent (the centerpiece)
**Folder:** `team_b/langgraph_agent/`

Imagine an assembly line with 13 stations. A request travels down it:

1. **Detect language** (English or Dzongkha)
2. **Speech-to-text** (if the input was audio)
3. **Translate** Dzongkha → English (so the rest works in English)
4. **Static guardrail** — a fast safety check for toxic or malicious input
5. **Fetch profile** — load the user's info (permissions, tier) from a database
6. **Classify intent** — what topic? (permit, health, tax, business, general)
7. **Contextual guardrail** — a smarter safety check that knows the user's permission level
8. **The orchestrator (ReAct agent)** — the brain that decides which tool to use
9. **Human handoff** — escalate to a real person if stuck
10. **Safety rejection** — the polite "I can't help with that" path
11. **Logger** — record every decision
12. **English speech-out**
13. **Dzongkha speech-out**

> **Say it like this:** "It's an assembly line. Each station does one job — safety,
> language, topic, action, logging. The star station is the 'orchestrator,' which can
> pick up *tools* and use them."

### 2. The tools (Team B's best feature)
**File:** `team_b/langgraph_agent/tools.py`

The orchestrator has real, working tools:

- **Business registration lookup** — find a business by its ID
- **Land registry lookup** — find a land parcel by plot/thram number
- **Tax compliance lookup** — check a business's tax status
- **Licensing board lookup**
- **Policy document search** (`retrieve_chunks`) — for general questions

These run on **fake demo data** right now, with clearly marked spots where the real
government APIs would plug in. But the *machinery* is real — this is the part of the
project that genuinely knows how to *do* something, not just talk.

> **One catch worth knowing:** the general "policy document search" tool only truly
> works if you connect a live cloud database (Supabase) that was never fully wired up.
> Without it, that tool just returns a list of *filenames* — so for general questions,
> Team B's agent can end up making up an answer from the AI's memory rather than from
> the real document. The **transaction** tools (land, tax, business) are the solid part.

### 3. The intent classifier + THE test set
**Folder:** `team_b/intent_classifier/`

This is quietly one of the most valuable things in the whole repo:
`bhutan_classifier_test_set_augmented_english.csv` — **234 real, hand-labelled test
questions** (36 original + 198 generated). It's the project's only real "answer key"
for measuring whether the system understands questions correctly.

Team B measured several classifiers against it and reported strong numbers
(a Gemini-based one scored ~97.9%). **Important nuance:** these measure whether the
system sorts a question into the right *bucket* — not whether the final *answer* is
correct. Those are different things.

### 4. Mock government endpoints
**Folder:** `team_b/mock_endpoints/`

Small, working fake versions of government services (tax assess/pay, land query,
business registration). These are the stand-ins for the real government systems and
are directly usable by other teams. The plan wants to **keep these** as the
transactional layer.

### 5. Contracts & schemas
**Folders:** `team_b/schemas/`, `contracts/`

Formal "agreement documents" (in JSON Schema form) describing exactly what a routing
request and response should look like, so different teams' code can talk to each other
reliably. This is careful, professional engineering.

---

## How a request flows (simplified)

```
Audio or text in
   │
   ▼
language → speech-to-text → translate → SAFETY CHECK → who is this user?
   │
   ▼
what topic? → SMARTER SAFETY CHECK → ORCHESTRATOR picks a tool
   │                                        │
   │                                        ├─ look up land record
   │                                        ├─ look up tax status
   │                                        ├─ look up business
   │                                        └─ search policy docs
   ▼
log the decision → speak the answer (English or Dzongkha)
```

Notice how many AI calls happen: the safety check, the smarter safety check, the
intent classifier, and the orchestrator each call the AI. **That's 4+ AI calls per
question** — the reason it's thorough but slow.

---

## What's genuinely good

- **The best transactional machinery in the project** — real tool-calling to look up
  specific records, with a fallback to a human when stuck.
- **The only real, labelled test set** — a genuine asset for measuring quality.
- **Two-layer safety** — a fast check plus a permission-aware check.
- **Professional contracts and decision-trace logging** — well-engineered plumbing.
- **Working mock government endpoints** — reusable by everyone.

## What to be honest about

- **Slow: 20–40 seconds per answer** (their own target), and rate-limited to one
  request every two seconds. Fine for a careful transaction, painful for a chat.
- **4+ AI calls per question** — more expensive and more places to go wrong.
- **The AI brain is Groq-hosted Llama-3.1-8B.** Groq is a proprietary cloud service —
  **you cannot buy a Groq chip and run it on Bhutan's own hardware.** So for the
  sovereign-GPU goal, this design would need real rewiring, not a settings change.
- **Smaller brain** — Llama-3.1-8B is much smaller/weaker than the prototype's Qwen3-32B.
- **General document search is a stub** (see the "one catch" note above).
- **Dzongkha via NLLB-600M translation**, which Team B's own notes admit is below the
  quality of Bhutan's national translation platform.
- Several **stale/broken imports** and empty report files — it's a rich prototype,
  not a finished product.

---

## How Team B relates to the prototype

They're not enemies — they're complementary. The prototype is better at the *brain*
(bigger model), *informational answers* (grounded + honest), *Dzongkha* (quote human
text), and *speed* (one call). Team B is better at *transactions* (real tools) and
*layered safety*. The stated plan is to **keep Team B's tools and mock endpoints** as
the "take action" layer and use them only when a real transaction is needed — not for
every question.

---

## The one thing to remember

> **Team B built the elaborate, action-taking agent — genuinely the best at looking up
> specific records, and the owner of the project's only real test set — but it's slow,
> makes many AI calls, and its brain runs on a rented Groq service that can't move onto
> the government's own hardware.**

---

## Words you can drop to sound like you know it

- **Agent / agentic** — software that takes actions using tools, not just chats.
- **LangGraph** — the framework Team B used to build the 13-step assembly line.
- **ReAct** — a pattern where the AI loops: Think → Act (use a tool) → Observe → repeat.
- **Tool-calling** — the AI deciding to run a function (like "look up this land plot").
- **Guardrail** — a safety check that blocks unsafe or out-of-bounds requests.
- **Groq** — the fast, *proprietary* cloud service running Team B's AI (the sovereignty blocker).
- **Transaction vs. information** — *doing* something for you vs. *telling* you something.
- **Decision-trace logging** — recording every step the agent took, for auditing.
