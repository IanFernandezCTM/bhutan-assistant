# Speaker Script — Bhutan Voice-First

*Read this aloud, one section per slide. Plain language, ~30–60 seconds each. Total run time ≈ 10–12 minutes.*
*Tip: press **F** for fullscreen, then use **→** to advance. Lines in italics are stage cues, not spoken.*

---

## Slide 1 — Title

*On screen: "From four teams to one sovereign product."*

"Good [morning/afternoon], everyone. Today I want to walk you through the Bhutan Voice-First assistant.

The idea is simple. A citizen speaks a question — in Dzongkha or English — and the government answers, out loud, from official documents. Many of the people we're serving can't read, so voice isn't a feature here; it *is* the product.

Four different teams built the pieces. What I'll show you is how those pieces came together into one working product — one that's built to run on hardware the government owns. And throughout, one rule guides everything: wrong information is unacceptable.

Let's start with how it all fits together."

*Advance.*

---

## Slide 2 — Overview

*On screen: the left-to-right flow — Voice → Understand → Act → Trace → Answer.*

"Here's the whole system in one picture. Follow the arrows.

First, **Team C** handles voice — turning what the citizen says into text. Then **Team A's NLP** track understands the words: what language, what they want, and any ID numbers. If the citizen wants an *action* — like checking their own record — **Team B's** tools take over. **Team D** stamps and logs every step so it's auditable. And finally, the **prototype** — the live product on the right — ties it all together and speaks the answer back.

So four teams built the parts, and the prototype unites them. Over the next four slides I'll introduce each team and what they do best. Then I'll set the real-world constraints, and show you exactly what the prototype kept, what it dropped, and how it works.

Let's meet the teams."

*Advance.*

---

## Slide 3 — Team A · NLP

*On screen: "Understanding the words" — two cards.*

"First, Team A's language team. Their job is to turn a raw sentence into structured facts.

They do three things. They **detect the language** — Dzongkha or English — instantly, just by looking at the script. They **classify the intent** — is this about land, tax, or civil registry — using keyword rules in both languages. And they **extract the important details** — a citizenship ID, a plot number, a year — with precise pattern-matching.

Why is this strong? It's fast, it's offline, and it needs no AI model and no API key — so it costs nothing to run. It's exact by design: an eleven-digit ID is copied character-for-character, never 'rephrased.' It's bilingual from day one. And it's so reliable that the final product reused this exact code.

That's the understanding layer. Now — taking action."

*Advance.*

---

## Slide 4 — Team B · Agentic

*On screen: "Taking action with tools" — two cards.*

"Team B built the most ambitious piece: an *agent* that doesn't just talk — it takes action.

They built a thirteen-step pipeline that runs a request through safety checks, language, intent, and then an orchestrator that can pick up *tools*. Those tools do real lookups — a business record, a land parcel, a tax status, a licence — by their ID number. They also built layered safety guardrails, mock government service endpoints, and formal contracts for how the pieces hand off.

Their strengths are real. This is the best 'do something for me' machinery in the whole project. They also produced the *only* properly labelled test set — 234 hand-checked questions — which is genuinely valuable. And their safety checks are permission-aware.

Hold on to two ideas here: real transactions, and the fact this runs on a lot of moving parts. Both matter later. Now — voice."

*Advance.*

---

## Slide 5 — Team C · Voice

*On screen: "The ears and the mouth" — two cards.*

"Team C are the ears and the mouth — and remember, voice is the whole point, because many of our users can't read.

On the way in, they do speech recognition: Whisper for English, a multilingual model for Dzongkha, with smart detection of when someone's actually speaking. On the way out, they do speech synthesis — a neural English voice and a Dzongkha voice. And they measured everything: accuracy and speed.

The results are encouraging. English listening is genuinely good — around seven to eleven percent word-error, comfortably under our twenty-percent target. They built a real, working voice loop — you can speak and be spoken to. And they were honest about the weak spot: they found that the slow part isn't the thinking, it's the *speaking*. That's a fixable problem, and knowing exactly where the delay is, is half the battle.

Last team — the glue that holds it together."

*Advance.*

---

## Slide 6 — Team D · Integration

*On screen: "The glue and the referee" — two cards.*

"Team D built the plumbing — and for a government service, this is not optional.

They put a unique tracking number — a trace ID — on every single request, so you can follow it through every step of the system. They made the logs *structured*, so they're searchable, not just walls of text. They wrote the one strict shared 'form' that every team fills out the same way, so the pieces actually fit together. And they built a dashboard to inspect it all.

Why it matters: this is what makes the system *auditable* — being able to prove exactly what it did and why. It's the most production-ready code in the whole project, and it was written to work with any framework, which is why the final product could simply adopt it.

So — that's the four teams, and each is genuinely good at something. But here's the catch. Being good in a demo isn't the goal."

*Advance.*

---

## Slide 7 — The Goal

*On screen: three big stats — Sovereign / 5,000+ / ~$13K.*

"This is the real finish line. Three hard constraints, and everything has to survive all three.

**One — sovereignty.** It has to run on a GPU the government owns. No citizen data ever leaves the network. That's the whole reason this project exists.

**Two — scale.** Five thousand or more conversations, every single day. Real citizen load, not a one-off demo.

**Three — cost.** One GPU, around thirteen thousand dollars, one time. Not a cloud bill that grows with every question a citizen asks.

These three limits aren't nice-to-haves. Together, they decide which of the teams' designs can actually reach production — and which one can't. Let me show you why."

*Advance.*

---

## Slide 8 — The Tension

*On screen: "punishes" vs "rewards" — two cards.*

"Here's the key insight: for this project, *more* is not *better*.

Look at what the goal punishes. Making many AI calls per question multiplies your cost and your delay. A brain that's welded to a proprietary cloud service can never move onto the government's own hardware. And heavy, multi-service stacks are fragile and expensive to run.

Now look at what the goal rewards. One AI call per question — cheap, fast, easy to scale. An open model you can download and host yourself. And a light footprint, with plain code used wherever it's cheaper and safer than AI.

This is the lens. Every 'keep it' or 'drop it' decision on the next slide comes straight from this. So let's see those decisions."

*Advance.*

---

## Slide 9 — Kept / Dropped

*On screen: the four-row matrix. Point to each row as you go.*

"This is the heart of it: what the prototype took from each team, and what it deliberately left behind — with the reason.

From **Team A**, we kept the language detection and entity extraction, the policy documents, the app shell, and the test questions. We dropped their four-call classifier and an old, unverified ninety-five-percent accuracy claim — because one grounded call now does the work of four, and real document retrieval replaces the old lookup.

From **Team B**, we kept the mock government endpoints — we actually re-packaged them into a sovereign lookup module — plus the logging and the tests. We dropped the thirteen-step agent and its Groq brain as the default, because it's too many calls, and Groq simply can't run on Bhutan's own GPU.

From **Team C**, we kept voice as the core, the connection contract, and their Dzongkha findings. We dropped the standalone scripts and the slow live-speech approach, replacing them with proper services and pre-recorded official audio.

And from **Team D**? We kept almost everything — the tracing, the schema, the dashboard — because it was built for exactly this.

The principle in one line: keep a piece only where it serves the goal. Now let me show you how the thing you're left with actually works."

*Advance.*

---

## Slide 10 — How It Works

*On screen: the five-step pipeline + three cards.*

"Here's the entire prototype, following one question through it.

Step one, **enrich**: detect the language and pull out any ID — plain code, no AI. Step two, **retrieve**: find the relevant policy passages, in English and the matching Dzongkha. Step three — the important one — **a single AI call**: it produces the answer, decides if it's in scope, checks it's safe, and picks the topic, all at once, grounded only in those passages. Step four, **transact**: *only* if there's an ID, it looks up the record. Step five, **speak**: translate if needed and say it out loud.

And notice the three promises at the bottom. It's **grounded** — it answers only from official documents, never guesses. It **abstains** — if it doesn't know, it says 'I don't have that, here's the office,' which is far better than a confident wrong answer. And it's **exact** — numbers and IDs are copied word-for-word, and Dzongkha is quoted from human-written text, never invented.

One honest call, per question. Which brings me to the single most important idea."

*Advance.*

---

## Slide 11 — The Sovereign Swap

*On screen: the three env-vars and the "rented cloud → on-prem" pills.*

"This is how we get to a government-owned GPU without rebuilding anything.

The app talks to its AI brain through just three settings — a web address, a key, and a model name. Today, that address points at a rented cloud running an open model called Qwen. To go fully sovereign, you change *one* setting to point at the government's own machine. That's it. Same open-weights model, same behavior, no rewrite — because it's the same model behind a standard socket.

And the numbers make the case. Five thousand conversations a day is less than one request every five seconds on average — the GPU sits idle most of the time. Running it in the cloud would cost only about a hundred and ten dollars a month, so to be clear: the GPU is about *ownership and control*, not beating the cloud on price. And it all works because there's just one call per question.

Now — one more thing we added recently."

*Advance.*

---

## Slide 12 — Sovereign Transactions

*On screen: two cards — "kept sovereign" and "one better".*

"Remember Team B's big strength — looking up your own records? We gave the prototype that power, without taking on Team B's cost.

The lookups now run *inside* the app — business, tax, land, and licence records — with no Groq and no second AI call. They're folded into that same single grounded call. And they only fire when there's a real ID in the question, so a normal question is never disrupted.

But we went one better. We added an ownership check: the citizen only sees the full record when their own ID matches the record's owner. Otherwise, it reveals nothing and asks them to verify who they are. Team B handed any record to anyone who knew the number — for a government service, that's not acceptable, and now it's fixed.

So we kept the capability, kept it sovereign, and made it safer. Let me sum up."

*Advance.*

---

## Slide 13 — Close

*On screen: "Grounded answers. Owned hardware. One call."*

"So, in one line: grounded answers, owned hardware, one call.

The prototype keeps the best of every team's work. It drops what our three constraints simply can't afford. And it's the only design that reaches a sovereign, government-owned GPU by changing a single setting.

That's the Bhutan Voice-First assistant. Thank you — I'm happy to take any questions."

*End.*

---

### Quick delivery notes
- **Pace:** aim for ~45 seconds a slide; don't rush slides 7 and 9 — they're the turning points.
- **If you have only 5 minutes:** show slides 1, 7, 9, 10, 11 — the goal and the synthesis carry the whole story.
- **Likely questions & one-line answers:**
  - *"Is it as good as Team B?"* → "Better where it matters — the model and grounded answers — and now it does Team B's transactions too, more safely."
  - *"What about the 95.1% accuracy?"* → "That was an old, unverified number; we dropped it. The real quality lever is grounding and abstention, and a proper end-to-end evaluation is the next step."
  - *"Why not just use the cloud?"* → "Sovereignty. Real citizen data must stay on hardware the government owns; the cloud is only for the synthetic-data demo."
