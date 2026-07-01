# Team D — Integration & Infrastructure

*The "make everything traceable and speak the same language" team.*

---

## The 30-second version (say this out loud)

> "Team D is the glue and the referee. They don't build the AI or the voice — they
> build the plumbing that lets all the other teams' pieces work together and be
> audited. Three things: first, a **logging system** that stamps every request with a
> unique tracking number (a 'trace ID') so you can follow it through every step;
> second, a **shared data format** — a strict contract for what an 'understood
> question' looks like — so Team A's output and Team B's input actually fit together;
> and third, a **dashboard** to inspect all those traces. It's the most
> production-shaped, professionally-engineered corner of the whole repo."

That's Team D. Details below.

---

## Why this team exists

Picture five teams building five pieces of one machine. Team A understands the
question, Team B takes action, Team C handles voice. If each team invents its own way
of describing a request, the pieces won't connect — and when something goes wrong,
nobody can tell *which* piece failed.

Team D solves both problems: a **common language** so the pieces fit, and a
**tracking system** so every step is recorded and auditable. For a **government**
service, that auditability isn't optional — you must be able to prove what the system
did and why.

---

## What they built (in plain English)

**Folder:** `team_d_integrations/`

### 1. Structured logging with a trace ID (the core contribution)
**Folder:** `team_d_integrations/service_logging/`

Every request gets a unique tracking number that looks like `TRC-XXXXXXXX`. That
number rides along with the request through every step — language detection,
document search, the AI call, routing, the answer. Every log line includes it.

> **Say it like this:** "It's like a parcel tracking number. One ID follows the request
> from the front door to the answer, so you can replay exactly what happened at every
> stop. That's how you audit a government system."

The logs aren't messy text — they're **structured** (clean JSON records with fixed
fields: time, level, trace ID, which service, what event, any error). That means you
can search and analyze them automatically, not just read them by eye.

The clever bit: the *core* of this logging is **framework-agnostic** — it doesn't
care whether the app is built with Flask (like the prototype) or FastAPI. So the
prototype was able to adopt it. (In the prototype it lives in `obs.py`, and it stamps
every chat with a trace ID.)

### 2. The canonical intent schema (the shared contract)
**Folder:** `team_d_integrations/test_nlp_intent_schema/`

This is a **strict, written-down definition** of what a "classified question" must
look like when one team hands it to another. It's a JSON Schema — think of it as a
form with required fields and rules about what can go in each.

The current version (**v2**) says every classified request must contain:

- a unique `request_id`,
- the `input` (the text and its language),
- a `classification` — the intent, which must be one of five official categories:
  **INFO** (wants information), **NAV** (wants directing somewhere), **TRANS** (wants
  a transaction done), **CLARIF** (needs clarification), **ESCL** (escalate to a
  human) — plus a confidence score and a "low confidence" flag,
- and `metadata` about which model produced it.

> **Say it like this:** "It's the official form that every team fills out the same way.
> Team A produces it, Team B consumes it. Because the form is strict, the handoff can't
> silently break."

### 3. The trace dashboard (the inspector)
**Folder:** `team_d_integrations/trace_dashboard/`

A terminal tool that reads all those trace logs and lets you **list, view, and search**
them — checking each one against the official format. This is how you'd verify the
"100% of actions are traced" goal.

### 4. Demo gateway & conversational shell
**Folders:** `team_d_integrations/gateway/`, `conversational_shell/`

Small demo apps that show the logging and trace-passing working end to end. They're
demonstrations of the plumbing, not the real assistant — they don't do NLP or voice
themselves.

---

## How the other teams use Team D's work

- **The prototype adopted the logging idea** — its `obs.py` stamps every chat with a
  trace ID and writes structured logs, following Team D's schema.
- **The intent schema is the agreed handoff format** between the language team and the
  routing/agent team — `intent_schema.py` in the prototype maps the assistant's output
  into Team D's canonical shape and validates it.
- **Team B writes decision-trace logs** in a shape the dashboard can read.

---

## What's genuinely good

- **The most production-shaped code in the repo** — careful, well-structured, tested.
- **Trace IDs everywhere** — the foundation of auditability, which a government service
  legally and practically needs.
- **A real, strict shared contract** — the thing that stops teams from drifting apart.
- **Framework-agnostic core** — reusable, which is why the prototype could adopt it.

## What to be honest about

- **A wiring gap between the two logging halves:** Team D's own logger writes to one
  folder, but the dashboard reads a slightly different trace format from another
  folder. So logs from one path don't automatically show up in the dashboard unless
  also written in the other shape. It's a reconciliation, not a rewrite — but it's
  not seamless yet.
- **The canonical schema has two versions (v1 and v2), and the automated tests only
  cover v1** — v2 (the one actually used) is under-tested.
- **The schema's list of allowed AI models excludes** the ones the prototype actually
  uses (Gemini, keyword) — so the prototype's output needs a small reconciliation to
  pass strict validation. A known open item.
- **Some intended documents are empty** (e.g. `docs/integration_spec.md` is a 2-byte
  file) — the real contracts live in code and JSON Schema files, not in the doc that
  was supposed to hold them.
- The dashboard and shells are **inspection/demo tools**, not the live service.

---

## How Team D relates to the whole project

Team D is the connective tissue. If Team A is the brain, Team B the hands, and Team C
the ears and mouth, **Team D is the nervous system and the medical chart** — it carries
signals between the parts and keeps a complete, auditable record of everything that
happened. The plan explicitly says most of Team D's work **survives**: trace logging,
the canonical schema, and the performance/latency harness are all kept.

---

## The one thing to remember

> **Team D built the plumbing that makes the project auditable and interoperable — a
> trace ID on every request, structured logs, a strict shared 'form' for classified
> questions, and a dashboard to inspect it all. It's the most professional code in the
> repo, and most of it is kept going forward.**

---

## Words you can drop to sound like you know it

- **Trace ID** — a unique tracking number (`TRC-XXXX`) that follows one request everywhere.
- **Structured logging** — logs as clean, searchable data (JSON), not loose text.
- **Canonical schema** — the one official, agreed data format everyone must use.
- **JSON Schema** — a strict, machine-checkable definition of what valid data looks like.
- **INFO / NAV / TRANS / CLARIF / ESCL** — the five official intent categories.
- **Auditability** — being able to prove exactly what the system did and why.
- **Framework-agnostic** — works regardless of whether the app uses Flask or FastAPI.
- **Interoperability** — different teams' components fitting together cleanly.
