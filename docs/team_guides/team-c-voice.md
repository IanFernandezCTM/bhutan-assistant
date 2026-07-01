# Team C — Voice (Speech In & Out)

*The "ears and mouth" team.*

---

## The 30-second version (say this out loud)

> "Team C handles voice — the ears and the mouth of the system. They built scripts
> that listen to a spoken question and turn it into text (that's ASR, speech
> recognition), and that take a written answer and speak it out loud (that's TTS,
> text-to-speech), for both English and Dzongkha. Their English speech recognition is
> genuinely good — well under the accuracy target. The main problems: the whole thing
> is slow, mostly because speaking the answer takes a long time, and Dzongkha is
> handled by translating to English and back, rather than natively. And it's built as
> standalone scripts, not as a reusable service other teams can easily plug into."

That's Team C. Details below.

---

## Why this team exists

The project's whole reason for being is that **many citizens can't read.** So voice
isn't a nice extra — it *is* the product. A citizen must be able to **speak** a
question and **hear** the answer. Team C owns that: converting speech to text on the
way in, and text to speech on the way out.

Two technical terms you'll use constantly:

- **ASR** = Automatic Speech Recognition = **listening** (speech → text).
- **TTS** = Text-to-Speech = **speaking** (text → speech).

---

## What they built (in plain English)

Team C's work is a set of Python scripts, split by language.

### English side
**Folder:** `team_c_voice/team-c-voice/English/`

- **`English_asr.py`** — records you from the microphone, uses **Whisper** (OpenAI's
  speech-recognition model) to turn your speech into text. It uses a helper called
  **Silero VAD** ("Voice Activity Detection") to notice when you're actually talking
  versus silent, so it doesn't transcribe background noise.
- **`English_tts.py`** — the *full* demo loop: record → recognize speech → ask an AI
  (Groq) → **speak the answer** using **Microsoft Edge's** neural voice.
- **`English_wer.py`** — a test script that measures how accurate the speech
  recognition is.

### Dzongkha side
**Folder:** `team_c_voice/team-c-voice/Dzongkha/`

- **`DZ_asr.py`** — records Dzongkha speech and sends it to **Facebook's MMS** model
  (a multilingual speech recognizer) over the internet to get text back.
- **`DZ_tts.py`** — speaks Dzongkha using **Facebook's MMS-TTS-dzo** voice model.
  Notably, it works by a **translation bridge**: Dzongkha question → translate to
  English → ask the AI → translate answer back to Dzongkha → speak it.
- **`DZwer.py`** — the Dzongkha accuracy test script.

### Benchmark
**Folder:** `team_c_voice/asr/` — a script that measured Whisper's accuracy on a
standard English audio dataset.

---

## The key results (the numbers to quote)

**English speech recognition accuracy** — measured as **WER (Word Error Rate)**, which
is "what fraction of words did it get wrong." Lower is better. The project's target is
**under 20%.**

| Whisper model | Word Error Rate | Verdict |
|---|---|---|
| tiny (fastest) | **11.2%** | ✅ beats the 20% target |
| medium (more accurate) | **6.6%** | ✅ comfortably beats it |

On a handful of Bhutan-specific test sentences ("I want to apply for land
registration," etc.) it scored **perfectly**.

> **Say it like this:** "English listening is a solved problem here — around 7–11%
> word error, well inside the under-20% target."

**Speed (end-to-end):** a full spoken exchange took **25–64 seconds**. The breakdown
is the important part:

- Listening (ASR): 2–7 seconds
- Thinking (the AI): ~1–5 seconds (fast!)
- **Speaking the answer (TTS): 13–50 seconds** ← this is the bottleneck

> **Say it like this:** "The slow part isn't the thinking — it's the *speaking*. TTS
> dominates the delay. Fixing voice latency means fixing how the answer is spoken, not
> how it's understood."

**Dzongkha:** the tools run, but there are **no real accuracy numbers** for Dzongkha
speech recognition, and the approach leans on **translation** rather than
understanding Dzongkha directly — which limits how authentic and trustworthy it is.

---

## What's genuinely good

- **English ASR is strong and proven** — comfortably beats the accuracy target.
- **Real end-to-end voice loop exists** — you can genuinely speak and be spoken to.
- **They measured latency honestly** and identified the real bottleneck (speaking).
- **Both languages attempted**, including a working Dzongkha voice.

## What to be honest about

- **Too slow for natural conversation** (25–64 seconds), and the cause is clearly the
  text-to-speech step.
- **Not a reusable service.** These are standalone scripts that start recording the
  moment you run them — other teams can't easily import and call them. The prototype
  had to build its own "adapter" with a fixed contract (`{transcript, confidence,
  language}`) to work around this.
- **Dzongkha is a translation bridge, not native** — Dzongkha → English → answer →
  Dzongkha. Meaning and numbers can drift in that round trip.
- **Heavy dependencies and many API keys** (Groq, Gemini, Google Translate, Hugging
  Face) — operationally fragile, no error handling if a service is down.
- **Sparse test data logged** (only 3 English results saved despite a 50-sentence script).
- The README is empty; the real write-up is in a PDF (`Team C Documentation.pdf`).

---

## How Team C relates to the prototype / the plan

The plan **keeps voice as core** and keeps Team C's **findings and the adapter
contract**, but replaces the non-importable scripts with proper *services*:

- English listening → **faster-whisper** (an optimized Whisper).
- Dzongkha listening → a maintained open model (omniASR), with fine-tuning planned.
- English speaking → **Kokoro** (a high-quality open voice).
- Dzongkha speaking → the clever fix: **pre-record the answers.** Because the set of
  policy answers is fixed and known, you can record a human (or vetted voice) saying
  each official section *once*, and just play the recording. Perfect quality, instant,
  no live-speaking delay, and fully local.

> **Say it like this:** "Team C proved English voice works and found that *speaking* is
> the slow part. The plan's answer for Dzongkha is elegant — don't generate the speech
> live, pre-record the fixed set of official answers and just play them back."

---

## The one thing to remember

> **Team C are the ears and mouth. English listening is proven and accurate; the
> system's slowness comes from *speaking*, not understanding; and Dzongkha still needs
> a better, more native approach than the current translate-and-back bridge.**

---

## Words you can drop to sound like you know it

- **ASR (Automatic Speech Recognition)** — listening: turning speech into text.
- **TTS (Text-to-Speech)** — speaking: turning text into audio.
- **Whisper** — OpenAI's speech-recognition model (the English workhorse here).
- **WER (Word Error Rate)** — the accuracy score for listening; lower is better; target < 20%.
- **VAD (Voice Activity Detection)** — detecting when someone is actually speaking.
- **MMS / MMS-TTS-dzo** — Facebook's multilingual speech models used for Dzongkha.
- **Latency** — total delay; here it's dominated by the speaking (TTS) step.
- **Adapter / contract** — the agreed shape of data (`transcript, confidence, language`)
  the rest of the system expects from voice.
