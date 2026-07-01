# Container for GCP Cloud Run (and any container host).
# Cloud Run injects $PORT (default 8080); app.py reads it. gunicorn serves app:app.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/hf

# CPU-only PyTorch (much smaller than the default CUDA build) for live Dzongkha
# TTS (MMS-TTS-dzo). Installed before requirements so transformers uses it.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the MMS-TTS-dzo weights into the image so cold starts don't download them.
RUN python -c "from transformers import AutoTokenizer, VitsModel; m='facebook/mms-tts-dzo'; AutoTokenizer.from_pretrained(m); VitsModel.from_pretrained(m)"

COPY . .

ENV PORT=8080
# 1 worker (single in-process TTS model to bound memory) x 8 threads; generous
# timeout for first-request model load. Plenty for ~5k conversations/day.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 app:app
