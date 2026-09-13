"""Application configuration loaded from environment variables."""

from decimal import Decimal
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Values are read from the project .env file when present."""

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    llm_provider: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    # Optional explicit OpenAI-compatible endpoint (e.g. a local Ollama/vLLM server, or a
    # hosted open-weight inference provider). Overrides the built-in default for llm_provider.
    llm_base_url: str | None = None
    # Actions valued at or above this amount require human approval regardless of action type.
    approval_threshold_inr: Decimal = Decimal("50000")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def llm_is_configured(self) -> bool:
        """True only when the agent has the configuration it needs."""
        is_local = (self.llm_provider or "").strip().lower() in ("ollama", "vllm", "lmstudio", "llamacpp")
        has_key = bool(self.llm_api_key and self.llm_api_key.get_secret_value())
        return bool(
            self.llm_provider
            and (has_key or is_local)
            and self.llm_model
        )

    @property
    def llm_configuration_message(self) -> str | None:
        if self.llm_is_configured:
            return None
        return (
            "LLM is not configured. Copy .env.example to .env and set "
            "LLM_PROVIDER, LLM_API_KEY, and LLM_MODEL before starting an investigation."
        )


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def update_llm_settings(
    provider: str | None = None,
    api_key: str | SecretStr | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> Settings:
    """Safely update LLM settings at runtime without storing secrets in plain text."""
    settings = get_settings()
    if provider is not None:
        settings.llm_provider = provider.strip() if provider.strip() else None
    if model is not None:
        settings.llm_model = model.strip() if model.strip() else None
    if base_url is not None:
        settings.llm_base_url = base_url.strip() if base_url.strip() else None
    if api_key is not None:
        if isinstance(api_key, SecretStr):
            settings.llm_api_key = api_key
        elif isinstance(api_key, str) and api_key.strip():
            settings.llm_api_key = SecretStr(api_key.strip())
        else:
            settings.llm_api_key = None
    return settings


def reset_llm_settings() -> Settings:
    """Reset LLM configuration back to unconfigured state (deterministic fallback)."""
    settings = get_settings()
    settings.llm_provider = None
    settings.llm_api_key = None
    settings.llm_model = None
    settings.llm_base_url = None
    return settings

