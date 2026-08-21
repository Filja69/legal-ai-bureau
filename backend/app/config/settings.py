"""Application settings — single source of truth, loaded from environment.

No secret ever has a default value here; missing required secrets fail
startup loudly instead of silently falling back to something insecure.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Sentinel, not a real secret — `Settings.assert_production_safe()` refuses to
# let the app boot with this value when ENVIRONMENT=production (Phase 9 audit
# §8/§15: this field previously had no such check, so a deployment that forgot
# to set JWT_SECRET would boot successfully and sign tokens with a secret
# that's public in this repository's source).
_INSECURE_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "legal-ai-bureau"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    database_url: str = Field(default="postgresql+asyncpg://legal:legal@localhost:5437/legal_ai_bureau")
    redis_url: str = Field(default="redis://localhost:6391/0")

    jwt_secret: str = Field(default=_INSECURE_DEFAULT_JWT_SECRET)
    jwt_algorithm: str = Field(default="HS256")
    jwt_expires_minutes: int = Field(default=60 * 12)
    jwt_issuer: str = Field(default="legal-ai-bureau")
    jwt_audience: str = Field(default="legal-ai-bureau-api")

    # Phase 7 brief §7 — dev-only bypass of real JWT validation. Defaults to
    # False everywhere; must be explicitly opted into (tests do so via
    # tests/conftest.py's environment setup, never silently). Even when
    # True, it never applies when environment == "production" (defense in
    # depth against a misconfigured prod deployment inheriting a dev .env).
    auth_dev_mode: bool = Field(default=False)

    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    llm_provider: str = Field(default="mock")  # mock | anthropic | openai
    llm_max_retries: int = Field(default=3)
    llm_timeout_seconds: float = Field(default=60.0)

    storage_provider: str = Field(default="local")  # local | s3
    storage_bucket: str | None = Field(default=None)
    # Only read when storage_provider="local". None (the default) preserves
    # the pre-existing repo-relative var/documents/ path — local dev/test
    # behavior is unaffected unless this is explicitly set. Set to a mounted
    # persistent Volume's path (e.g. Railway) so uploads survive redeploys —
    # a PaaS container filesystem is otherwise ephemeral (see
    # app/documents/storage/base.py's DocumentStorage docstring).
    local_storage_path: str | None = Field(default=None)
    # S3-compatible object storage (staging deployment target §9) — only read
    # when storage_provider="s3". Deliberately not bound to AWS-only naming
    # (S3_ENDPOINT_URL lets any S3-compatible provider be used, not just AWS).
    s3_endpoint_url: str | None = Field(default=None)
    s3_access_key_id: str | None = Field(default=None)
    s3_secret_access_key: str | None = Field(default=None)
    s3_region: str = Field(default="us-east-1")

    # OCR (scanned-PDF fallback) — self-hosted Tesseract only, see
    # app/documents/ocr/tesseract_engine.py for why this is never a cloud
    # OCR API or an LLM vision call. Disabled entirely still degrades
    # gracefully to the pre-existing OCR_REQUIRED status, never a crash.
    ocr_enabled: bool = Field(default=True)
    ocr_language: str = Field(default="rus+eng")
    ocr_dpi: int = Field(default=200)
    # Hard ceiling, not a performance tuning knob (same "fails closed rather
    # than silently degrading" philosophy as embedding_max_documents_per_reindex
    # below) — OCR runs synchronously inside the upload request, so an
    # unbounded page count could hang it indefinitely.
    ocr_max_pages_per_document: int = Field(default=30)

    legal_source_official_law_base_url: str = Field(default="https://pravo.gov.ru")
    legal_source_court_base_url: str = Field(default="https://kad.arbitr.ru")
    legal_source_commercial_db_enabled: bool = Field(default=False)

    # RAG / embeddings (LEGAL-RAG.md §1, Phase 2) — never hardcode the dimension
    # at call sites; app.models.embedding_chunk.EmbeddingChunk reads it once at
    # import time to size the pgvector column. Changing EMBEDDING_DIMENSION after
    # data has been indexed requires a new migration + full reindex, not a config
    # flip — the value is baked into the column type, not just app-level config.
    embedding_provider: str = Field(default="mock")  # mock | openai
    embedding_model: str = Field(default="mock-embedding-v1")
    embedding_dimension: int = Field(default=1536)
    embedding_batch_size: int = Field(default=96)
    embedding_timeout_seconds: float = Field(default=30.0)
    embedding_max_retries: int = Field(default=3)

    # Phase 6.5 cost/safety limits (brief §3) — a bulk reindex against a real
    # paid provider must never silently run away. These are hard ceilings,
    # not a billing system: exceeding one fails the operation closed.
    embedding_max_documents_per_reindex: int = Field(default=5000)
    embedding_max_requests_per_minute: int = Field(default=500)

    default_jurisdiction: str = Field(default="RU")
    default_language: str = Field(default="ru")

    log_level: str = Field(default="INFO")

    # Phase 9 audit §15 — none of these existed before; the app had no CORS
    # policy, no upload limit, and no rate limiting at all.
    #
    # Staging audit finding (docs/STAGING-DEPLOYMENT-AUDIT.md §2): pydantic-
    # settings' default env decoding for a `list[str]` field tries JSON
    # first and raises SettingsError on a plain comma-separated string —
    # exactly how a human fills in an env var in a cloud dashboard. NoDecode
    # + the validator below accept either form.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_upload_size_bytes: int = Field(default=25 * 1024 * 1024)  # 25 MB
    rate_limit_auth_per_minute: int = Field(default=10)  # POST /auth/token, per client IP
    rate_limit_llm_per_minute: int = Field(default=20)  # research/contract-analyze, per workspace

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors_allowed_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    def assert_production_safe(self) -> None:
        """Fail loudly at startup rather than booting insecurely — called from
        `app.main.create_app()`. Never call this from a request path; it's a
        one-time boot-time gate, not a per-request check.

        Staging audit finding (docs/STAGING-DEPLOYMENT-AUDIT.md §3): this used
        to only trigger on the literal string "production", so a staging
        deployment set to ENVIRONMENT=staging silently skipped every check
        here. Flipped to the opposite polarity — "development" is the only
        environment value permitted to be lax; anything else (production,
        staging, a typo) gets the strict checks. This mirrors the same
        tightening applied to the AUTH_DEV_MODE bypass in
        app/security/deps.py and the JSON log renderer in app/core/logging.py.
        """
        if self.environment == "development":
            return
        if self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise RuntimeError(
                f"JWT_SECRET is set to the insecure development default while ENVIRONMENT={self.environment!r}. "
                "Set a real, random JWT_SECRET before starting the app outside local development."
            )
        if self.debug:
            raise RuntimeError(
                f"DEBUG=true while ENVIRONMENT={self.environment!r} — this can leak stack traces. Refusing to start."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
