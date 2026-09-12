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
        """True only when the future agent has the configuration it needs."""
        return bool(
            self.llm_provider
            and self.llm_api_key is not None
            and self.llm_api_key.get_secret_value()
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
