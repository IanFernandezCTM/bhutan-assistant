# Bhutan Public Services Assistant

Voice-first AI assistant for Bhutan public services, built by Omdena Sprint Team 4.

- **Backend**: Flask + Gemini classifier + conversation engine + knowledge base
- **Frontend**: Single-page chat UI styled to match the Omdena visual brand
- **Dev mode**: Toggle in the header reveals per-message classification (in-scope / safety / request type / service) with confidence scores

---

## Run locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Gemini key (recommended) — or leave it hardcoded in app.py for now
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
├── app.py              # Flask backend (your classifier + engine)
├── templates/
│   └── index.html      # Frontend (Omdena-styled chat UI)
├── requirements.txt
├── Procfile            # web: gunicorn app:app
├── render.yaml         # Render deployment config
├── .gitignore
└── README.md
```

---

## API

`POST /api/chat`

```json
{ "message": "What documents do I need for a construction permit?" }
```

Response:

```json
{
  "bot_text": "Great! Let me guide you through that…",
  "sources": ["bhutan_flow_docs/permits"],
  "step_label": "Step 3 of 4",
  "fallback_id": null,
  "ref_no": "REF-A1B2C3D4",
  "classification": {
    "in_scope":     { "label": "in_scope",         "confidence": 0.97 },
    "safety":       { "label": "safe",             "confidence": 0.99 },
    "request_type": { "label": "document_inquiry", "confidence": 0.94 },
    "service":      { "label": "permits",          "confidence": 0.98 }
  },
  "classifier_kind": "GeminiClassifier"
}
```
