"""API routes for safe runtime LLM configuration and connection testing."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.config import get_settings, reset_llm_settings, update_llm_settings
from backend.llm.provider import test_llm_provider_connection


class LLMConfigRequest(BaseModel):
    provider: str | None = Field(default=None, description="LLM provider name (e.g. ollama, groq, vllm, lmstudio)")
    api_key: str | None = Field(default=None, description="API key (never logged or returned in responses)")
    model: str | None = Field(default=None, description="Model identifier")
    base_url: str | None = Field(default=None, description="Optional custom base URL")
    test_connection: bool = Field(default=True, description="Whether to test connection immediately")


class LLMConfigResponse(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    is_configured: bool = False
    has_api_key: bool = False
    connection_status: str = "not_tested"  # "ok", "error", "not_tested", "not_configured"
    status_message: str | None = None


class LLMTestResponse(BaseModel):
    success: bool
    message: str


router = APIRouter(prefix="/llm", tags=["llm-config"])


def _build_config_response(connection_status: str = "not_tested", custom_message: str | None = None) -> LLMConfigResponse:
    settings = get_settings()
    has_key = bool(settings.llm_api_key and settings.llm_api_key.get_secret_value())

    msg = custom_message or settings.llm_configuration_message
    if connection_status == "not_configured":
        msg = "LLM is not configured. Running in deterministic fallback mode."
    elif connection_status == "ok" and not custom_message:
        msg = f"LLM configured and verified ({settings.llm_provider} / {settings.llm_model})."

    return LLMConfigResponse(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        is_configured=settings.llm_is_configured,
        has_api_key=has_key,
        connection_status=connection_status,
        status_message=msg,
    )


@router.get("/config", response_model=LLMConfigResponse)
def get_llm_config() -> LLMConfigResponse:
    """Return safe LLM configuration status. Never returns secret API keys."""
    settings = get_settings()
    status = "not_configured" if not settings.llm_is_configured else "not_tested"
    return _build_config_response(connection_status=status)


@router.post("/config", response_model=LLMConfigResponse)
def set_llm_config(req: LLMConfigRequest) -> LLMConfigResponse:
    """Update runtime LLM settings safely."""
    settings = get_settings()

    key_to_use = req.api_key
    if key_to_use is None and settings.llm_api_key:
        key_to_use = settings.llm_api_key

    updated = update_llm_settings(
        provider=req.provider,
        api_key=key_to_use,
        model=req.model,
        base_url=req.base_url,
    )

    if not updated.llm_is_configured:
        return _build_config_response(connection_status="not_configured")

    if req.test_connection:
        ok, msg = test_llm_provider_connection(updated)
        conn_status = "ok" if ok else "error"
        return _build_config_response(connection_status=conn_status, custom_message=msg)

    return _build_config_response(connection_status="not_tested")


@router.delete("/config", response_model=LLMConfigResponse)
def clear_llm_config() -> LLMConfigResponse:
    """Clear LLM credentials and revert to deterministic fallback mode."""
    reset_llm_settings()
    return _build_config_response(connection_status="not_configured")


@router.post("/test", response_model=LLMTestResponse)
def test_llm_connection() -> LLMTestResponse:
    """Test connection to the currently configured LLM endpoint."""
    settings = get_settings()
    if not settings.llm_is_configured:
        return LLMTestResponse(success=False, message="LLM is not fully configured.")
    ok, msg = test_llm_provider_connection(settings)
    return LLMTestResponse(success=ok, message=msg)
