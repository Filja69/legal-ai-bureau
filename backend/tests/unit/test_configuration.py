from __future__ import annotations

import pytest

from app.config.settings import Settings, get_settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("APP_NAME", "legal-ai-bureau-test")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_name == "legal-ai-bureau-test"
    get_settings.cache_clear()


def test_settings_default_jurisdiction_is_ru():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.default_jurisdiction == "RU"
    assert settings.default_language == "ru"


def test_settings_llm_provider_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.llm_provider == "mock"
    get_settings.cache_clear()


# --- Phase 9 audit §8/§15: production must refuse to boot with an insecure default. ---


def test_assert_production_safe_allows_default_secret_outside_production():
    settings = Settings(environment="development")
    settings.assert_production_safe()  # must not raise


def test_assert_production_safe_rejects_default_jwt_secret_in_production():
    settings = Settings(environment="production", jwt_secret="dev-only-insecure-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.assert_production_safe()


def test_assert_production_safe_allows_real_secret_in_production():
    settings = Settings(environment="production", jwt_secret="a-real-random-secret-value")
    settings.assert_production_safe()  # must not raise


def test_assert_production_safe_rejects_debug_true_in_production():
    settings = Settings(environment="production", jwt_secret="a-real-random-secret-value", debug=True)
    with pytest.raises(RuntimeError, match="DEBUG"):
        settings.assert_production_safe()


def test_settings_have_security_defaults():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cors_allowed_origins == ["http://localhost:3000"]
    assert settings.max_upload_size_bytes == 25 * 1024 * 1024
    assert settings.rate_limit_auth_per_minute > 0
    assert settings.rate_limit_llm_per_minute > 0
    get_settings.cache_clear()


# --- Staging audit §3: "development" is the only lax environment value ---


def test_assert_production_safe_rejects_default_secret_in_staging():
    """Previously only the literal string "production" triggered this check
    — a staging deployment (ENVIRONMENT=staging) would have silently booted
    with the insecure default secret. See docs/STAGING-DEPLOYMENT-AUDIT.md §3.
    """
    settings = Settings(environment="staging", jwt_secret="dev-only-insecure-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.assert_production_safe()


def test_assert_production_safe_rejects_debug_true_in_staging():
    settings = Settings(environment="staging", jwt_secret="a-real-random-secret-value", debug=True)
    with pytest.raises(RuntimeError, match="DEBUG"):
        settings.assert_production_safe()


def test_assert_production_safe_allows_real_secret_in_staging():
    settings = Settings(environment="staging", jwt_secret="a-real-random-secret-value")
    settings.assert_production_safe()  # must not raise


# --- Staging audit §2: CORS_ALLOWED_ORIGINS must accept a plain env-var string ---


def test_cors_allowed_origins_accepts_comma_separated_string(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://legal-ai-bureau.vercel.app, http://localhost:3000")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cors_allowed_origins == ["https://legal-ai-bureau.vercel.app", "http://localhost:3000"]
    get_settings.cache_clear()


def test_cors_allowed_origins_still_accepts_json_array_string(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://a.example.com","https://b.example.com"]')
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cors_allowed_origins == ["https://a.example.com", "https://b.example.com"]
    get_settings.cache_clear()


def test_cors_allowed_origins_default_unaffected(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cors_allowed_origins == ["http://localhost:3000"]
    get_settings.cache_clear()
