"""Base API routes available before agent features are added."""

from fastapi import APIRouter

from backend.config import get_settings

from backend.api.runs import router as runs_router

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, object]:
    """Report application availability and actionable LLM configuration status."""
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "llm_configured": settings.llm_is_configured,
        "configuration_message": settings.llm_configuration_message,
    }


router.include_router(runs_router)

