# CallSense — Hugging Face Space image (REAL mode: faster-whisper + Gemini).
# HF free tier: 2 vCPU / 16GB RAM — comfortably fits Whisper small (int8).
# Boot: migrations → demo seed (audio generated in-container so playback works)
# → API with the worker running as an inline thread.

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements-real.txt ./
RUN pip install --no-cache-dir -r requirements-real.txt

# Bake the Whisper model into the image so cold starts don't download ~480MB.
ENV HF_HOME=/app/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

COPY backend/ ./
COPY demo/ /demo/

# HF Spaces run as a non-root user (uid 1000) and expect the app on port 7860.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /data/audio \
    && chown -R appuser:appuser /app /demo /data
USER appuser

ENV PORT=7860 \
    ENVIRONMENT=prod \
    MOCK_MODE=false \
    RUN_INLINE_WORKER=true \
    LLM_PROVIDER=gemini \
    GEMINI_MODEL=gemini-flash-lite-latest \
    WHISPER_MODEL=small \
    WHISPER_COMPUTE_TYPE=int8 \
    AUDIO_STORAGE_DIR=/data/audio \
    SEED_AUDIO_DIR=/data/audio/seed \
    PYTHONPATH=/app

EXPOSE 7860

CMD ["sh", "-c", "alembic upgrade head && python /demo/seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
