"""Application configuration.

Single source of truth for config, loaded from the environment (12-factor) and
validated at startup via pydantic-settings. A missing/mistyped value fails loud
at boot instead of cryptically mid-request.

Note: fields used only by later phases (LLM keys, Whisper model, watch folder)
are declared here already so there is *one* config story end-to-end.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -------------------------------------------------------------
    app_name: str = "CallSense"
    environment: str = "local"  # local | docker | ci | prod
    log_level: str = "INFO"

    # --- Database ---------------------------------------------------------
    # Default targets a locally-running Postgres. docker-compose overrides the
    # host to the `postgres` service via the DATABASE_URL env var.
    database_url: str = (
        "postgresql+psycopg://callsense:callsense@localhost:5432/callsense"
    )

    # --- Pipeline / worker (used from Phase 2+) --------------------------
    worker_poll_interval_s: float = 2.0
    job_max_attempts: int = 3
    job_backoff_base_s: float = 2.0

    # --- Analysis / LLM (used from Phase 4+) -----------------------------
    # MOCK_MODE=true runs the whole loop with canned fixtures and zero network
    # so graders without API keys still see the full system work.
    mock_mode: bool = True
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"  # rubric analysis (nuanced judgment)
    classifier_model: str = "claude-haiku-4-5-20251001"  # cheap sales/non-sales
    llm_temperature: float = 0.0

    # --- Transcription / diarisation (used from Phase 3+) ----------------
    whisper_model: str = "small"  # tiny|base|small|medium|large
    whisper_compute_type: str = "int8"
    hf_token: str | None = None  # optional; enables pyannote, else fallback

    # --- Ingestion (used from Phase 2+) ----------------------------------
    watch_folder: str = "./demo/audio/inbox"
    audio_storage_dir: str = "./demo/audio/store"

    @property
    def is_mock(self) -> bool:
        return self.mock_mode


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so config is parsed once per process."""
    return Settings()
