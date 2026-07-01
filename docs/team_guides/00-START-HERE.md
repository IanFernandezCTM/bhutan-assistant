# Bhutan Voice-First — Team Guides (Start Here)

*Read these five guides out loud, in order, and you'll understand the whole repository.*

---

## What this whole project is (say this first)

> "Bhutan Voice-First is a government assistant for citizens who may not be able to
> read. A citizen **speaks** a question in Dzongkha or English — about land, taxes,
> permits, a birth certificate — and the system finds the answer in Bhutan's official
> documents and **speaks it back** in the same language. The long-term goal is for it
> to run entirely on **hardware the government owns**, so no citizen data ever leaves
> the country's control. Wrong information is unacceptable, so the system is built to
> stay grounded in official text and to say 'I don't know' rather than guess."

That single paragraph is the north star. Every team serves some part of it.

---

## The five teams, in one line each

| Team | Nickname | One-line job |
|---|---|---|
| **A — NLP** | *understand the words* | Detect the language, the intent, and pull out ID numbers. |
| **A — Prototype** | *the product* | The real, live web app that ties it all together. **This is the chosen path.** |
| **B — Agentic** | *take action* | An elaborate agent that uses tools to look up specific records. |
| **C — Voice** | *ears & mouth* | Turn speech into text (listening) and text into speech (speaking). |
| **D — Integration** | *the glue & referee* | Trace IDs, structured logs, a shared data contract, a dashboard. |

Read them in this order: **C → A-NLP → B → D → A-Prototype.** That follows the natural
flow of a request (voice in → understand → act → log → answer) and ends on the product
that unifies everything.

---

## How a citizen's question flows through the whole system

```
   🎙️  Citizen speaks
        │
        ▼
   [TEAM C]  Voice → text  (ASR: "listening")
        │
        ▼
   [TEAM A-NLP]  What language? What do they want? Any ID numbers?
        │
        ▼
   [look up the answer in official policy documents]
        │
        ▼
   [TEAM B]  If they want an ACTION (check my land record) → use a tool
   [A-PROTOTYPE]  If they want INFORMATION → one grounded AI call
        │
        ▼
   [TEAM D]  Stamp a trace ID, log every step, use the shared format
        │
        ▼
   [TEAM C]  Text → voice  (TTS: "speaking")
        │
        ▼
   🔊  Citizen hears the answer
```

---

## The three things that surprise everyone (know these and you sound expert)

1. **There are actually THREE separate "apps" in this repo, only one is the product.**
   The prototype (Flask, live on Google Cloud) is the real one. There's also a
   separate Streamlit experiment at the repo root, and Team B's LangGraph agent. Don't
   confuse them.

2. **There are THREE different document-search systems and they don't all connect.**
   The working one is basic word-matching. The "smart" vector-database one was never
   finished (it can file documents but not search them). This is the biggest gap.

3. **There are THREE different ways of naming intents.** Team A-NLP uses one set of
   labels, the prototype and Team B's classifier use another (4 dimensions), and Team
   D's official schema uses a third (INFO/NAV/TRANS/CLARIF/ESCL). Reconciling these is
   ongoing integration work.

---

## The single most important idea in the project

> **"Simulate local now, own it later."**
>
> The chosen product (the prototype) talks to its AI brain through a standard socket
> with three settings. Today the socket is plugged into a **rented cloud** AI. To make
> the system fully sovereign — running on **Bhutan's own GPU** — you change **one
> setting** to point at the local machine. Same open-weights model, same behavior, no
> rewrite. This is why the prototype was chosen: it's the only design built to move
> onto government hardware without being rebuilt.

---

## Honesty rules baked into this project (and these guides)

This project's charter explicitly treats **honest reporting as a success requirement** —
you don't round numbers up, hide bad results, or claim things the code can't back up.
So these guides flag, for every team, both what genuinely works and what's incomplete
or unverified. A famous example: the **"95.1% accuracy"** figure written in the
prototype's code is **unverified** and should not be quoted (see `PROVENANCE_AUDIT.md`).

If you repeat only the good parts, you're not a master of the repo — you're a
salesperson. Repeat both, and you'll sound like someone who truly knows it.

---

## Where to go deeper

- `REPO_MAP.md` — the exhaustive, file-by-file inventory of the whole repo.
- `LOCAL_FIRST_PLAN.md` — the plan for the sovereign-GPU, voice-first architecture.
- `PROVENANCE_AUDIT.md` — which claims are backed by evidence and which aren't.
- `GAP_REPORT.md` — the concrete integration gaps between teams.

---

## Your one-paragraph "master of the repo" summary

> "Five teams, one goal: let a non-literate Bhutanese citizen speak a question and hear
> a trustworthy answer from official documents, eventually all on the government's own
> hardware. Team C does voice in and out; Team A's NLP track understands the words;
> Team B builds an agent that can take actions with tools; Team D provides the tracing,
> logging, and shared contracts that hold it together; and Team A's Prototype is the
> live product that unifies it — built around one honest, grounded AI call per question
> and a design that can move from rented cloud to sovereign GPU by changing a single
> setting. The main open gaps are a half-finished document-search system, three
> intent-naming schemes that need reconciling, and Dzongkha voice quality — all known,
> all documented, none hidden."
