# CallSense backend image (shared by the api and worker services).
FROM python:3.11-slim

# ffmpeg/ffprobe: audio validation + decoding (used from Phase 2+).
# curl: container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8000

# Default command runs the API + applies migrations; the worker service in
# docker-compose overrides this with `python -m pipeline.worker`.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
