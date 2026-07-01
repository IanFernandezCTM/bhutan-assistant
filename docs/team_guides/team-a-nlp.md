# Team A — NLP Track

*The "understand the words" team.*

---

## The 30-second version (say this out loud)

> "Team A's NLP track is the language-understanding groundwork. It does two jobs.
> First, it reads a citizen's message and figures out three things: what language
> it's in, what the person wants, and any important details like an ID number or a
> plot number. Second, it has an early attempt at document search — pulling answers
> out of Bhutan's policy documents. The message-reading part works and was reused by
> the main product. The document-search part is half-finished: one version works but
> is basic, and the other version can only *file* documents away, not *find* them again."

That's the whole team in a paragraph. Everything below is just detail.

---

## Why this team exists

Before a computer can help a citizen, it has to understand what the citizen said.
A person might type (or speak) in **English** or in **Dzongkha**. They might ask
about land, taxes, a birth certificate, or just say hello. And they might mention a
specific number — "my plot 90" or "CID 11503012345" — that the system needs to grab
exactly right.

Team A's NLP track is the layer that turns a raw sentence into **structured facts**
the rest of the system can act on.

---

## What they built (in plain English)

Think of it as three tools in a toolbox. Two are for **understanding**, one is for
**searching**.

### Tool 1 — The intent classifier (works ✅)
**File:** `team_a_nlp/intent_classifier.py`

You give it a sentence. It gives you back a little report:

- **Language** — English or Dzongkha. It decides this with a simple, reliable trick:
  Dzongkha uses the Tibetan script, which lives in its own slice of the Unicode
  character table. If it sees any of those characters, it says "Dzongkha." No AI
  needed — just a character check.
- **Intent** — which of five buckets the request falls in:
  `land_registration`, `tax_query`, `civil_registry`, `greeting`, or `unknown`.
  It decides this by **keyword matching** in *both languages*. It literally has a
  list of English words and Dzongkha words for each topic, and counts the matches.
- **Entities** — the important specifics: a Citizenship ID (an 11-digit number),
  a plot ID, a tax year, a document type. It grabs these with **regular
  expressions** (pattern rules), which is exactly what you want for something like
  an ID number — you need it copied *perfectly*, and a pattern rule never
  "creatively rephrases" a number.

**The important thing to remember:** this tool is mostly **rules, not AI**. That
makes it fast, free, and predictable. There's an *optional* AI model
(`xlm-roberta-base`) it can fall back to for harder cases, but it's off by default
and isn't even in the requirements file — so in practice, it's the rules doing the work.

### Tool 2 — The RAG pipeline (works, but basic ✅⚠️)
**File:** `team_a_nlp/rag_pipeline.py`

"RAG" means **Retrieval-Augmented Generation** — a fancy term for "look up the
answer in real documents before responding." This version does the "look up" half.

It reads Bhutan's policy documents (plain-text files in `shared/policy_docs/`),
chops them into chunks, and when you ask a question it finds the chunks that share
the most words with your question. That's it — **word-overlap counting**. No deep
"meaning" understanding.

> **Say it like this:** "It's keyword search, like Ctrl-F on steroids — it finds
> chunks that share words with your question, but it doesn't understand *meaning*.
> Ask 'how much is the late penalty' and it'll match on the words, not the concept."

This is the one piece the main product actually borrowed and built on.

### Tool 3 — The ingestion pipeline (half-built ⚠️)
**Files:** `team_a_nlp/ingestion_pipeline.py`, `supabase_client.py`

This is the *ambitious* version of search that was never finished. The plan was:
take PDF documents → chop them up → run them through an AI model (**Ollama's
`nomic-embed-text`**) that turns text into "meaning vectors" → store those in a
cloud database (**Supabase** with **pgvector**).

Here's the catch, and it's the single most important fact about this team:

> **It can only put documents IN. There is no code to get them back OUT.**

It's a one-way street. It files everything away neatly and then has no "search"
button. So despite sounding like a real semantic search engine, **it doesn't
actually answer any questions yet.** It also needs external services running
(the Ollama program on the machine, plus a Supabase cloud account) to do even the
filing part.

---

## How it all fits together

```
Citizen's sentence
      │
      ▼
[Tool 1] intent_classifier.py  →  { language, intent, entities }   ← this works, and got reused
      │
      ▼
[Tool 2] rag_pipeline.py  →  finds matching policy chunks by word overlap   ← works, basic
      
[Tool 3] ingestion_pipeline.py  →  files PDFs into a cloud DB... but can't search them   ← dead end
```

---

## What's genuinely good here

- The **language detection and entity extraction actually work** — so well that the
  main product (Team A Prototype) **copied this exact logic** into its own
  `nlp_enrichment.py`. That's the real, lasting contribution.
- The **bilingual keyword lists** are real Dzongkha, not placeholders.
- It's **lightweight and offline** — the classifier needs no API keys and no heavy
  AI libraries.

## What's incomplete or misleading

- The README talks about a "vector database," which makes it sound like modern
  semantic search. In reality the *working* search is plain word-matching, and the
  *vector* version can't search at all.
- **No retrieval function** in the Supabase path — the biggest gap.
- **No tests** in this folder.
- A couple of small bugs (a file-path issue; a comment says it reads `.txt` files
  but the code actually reads `.pdf` files).

---

## The one thing to remember

> **Team A NLP's real gift to the project is the "understand the message" code —
> language + intent + entities — which the main product reused. Its document-search
> ambitions were only half-built: the simple version works, the smart version can
> file but not find.**

---

## Words you can drop to sound like you know it

- **Intent classification** — deciding what the user *wants* (land? tax? greeting?).
- **Entity extraction** — pulling out the specifics (ID numbers, plot numbers, dates).
- **RAG (Retrieval-Augmented Generation)** — look up real documents before answering.
- **Embeddings / vectors** — turning text into numbers that capture *meaning*, so a
  computer can find "similar" text. (This is what the unfinished pipeline was for.)
- **pgvector / Supabase** — the cloud database that was *supposed* to store those vectors.
- **Ingest-only** — the killer phrase: it can store, but not retrieve.
