"""FastAPI entry point for Adhyay."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Adhyay API",
    version="0.1.0",
    description="The local API for Adhyay's agentic operations investigator.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles

    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str) -> FileResponse:
        """Serve the built SPA for any non-API route, including a refresh on a deep link.

        FastAPI matches routes in registration order, and the ``/api`` router above is
        included first, so this catch-all can never shadow a real API endpoint.
        """
        candidate = frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")


if __name__ == "__main__":
    import uvicorn

    # Most PaaS hosts (Render, Railway, Fly.io) inject $PORT and require binding 0.0.0.0.
    port = int(os.environ.get("PORT", settings.app_port))
    host = os.environ.get("HOST", "0.0.0.0" if settings.app_env == "production" else settings.app_host)
    uvicorn.run("backend.main:app", host=host, port=port)
