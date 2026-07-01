# Deploy to GCP Cloud Run

The app now deploys on **Google Cloud Run** (replacing Render). The LLM is reached over an
OpenAI-compatible API today (DeepInfra / Qwen3-32B) and can later be pointed at an on-prem or
GCP-GPU vLLM server by changing one env var — no code change. See [LOCAL_FIRST_PLAN.md](../LOCAL_FIRST_PLAN.md).

## 0. Prerequisites
```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

## 1. Store the API key as a secret (never commit it)
```bash
printf '%s' '<YOUR_DEEPINFRA_KEY>' | gcloud secrets create LLM_API_KEY --data-file=-
# later rotations:  printf '%s' '<NEW_KEY>' | gcloud secrets versions add LLM_API_KEY --data-file=-
```

## 2. Deploy (from this directory: team_a_prototype/)
```bash
gcloud run deploy bhutan-assistant \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 1Gi --cpu 1 --concurrency 40 --min-instances 0 --max-instances 4 \
  --set-env-vars LLM_BASE_URL=https://api.deepinfra.com/v1/openai,LLM_MODEL=Qwen/Qwen3-32B,EMIT_CANONICAL_INTENT=1 \
  --set-secrets LLM_API_KEY=LLM_API_KEY:latest
```
`--source .` uses the included `Dockerfile`. Cloud Run sets `$PORT`; gunicorn binds to it.

## 3. Verify
```bash
curl https://<service-url>/healthz      # expect: "primary_path":"llm-first", llm.configured:true
```
Open the service URL → the GovTech-styled, bilingual, voice-first UI.

## 4. Going fully local / data-sovereign (later)
Stand up vLLM on the on-prem GPU (or a GCP GPU VM) serving the **same** Qwen3-32B weights, then:
```bash
gcloud run services update bhutan-assistant \
  --region asia-south1 \
  --set-env-vars LLM_BASE_URL=http://<vllm-host>:8000/v1,LLM_MODEL=Qwen/Qwen3-32B,LLM_API_KEY=EMPTY
```
Nothing else changes. For full data sovereignty, run the whole app on-prem and keep citizen data
off any hosted endpoint — the hosted API is only for the demo phase with synthetic/public queries.

## Notes
- **Region:** `asia-south1` (Mumbai) is the closest GCP region to Bhutan for latency/residency.
- **Data sovereignty:** the hosted DeepInfra endpoint sends prompts off-prem — use only
  synthetic/public test data on it; real citizen data must hit the on-prem vLLM server.
- The app still boots with **no** `LLM_*` set (offline keyword fallback), so a misconfigured
  deploy degrades instead of crashing.
