"""uzum-claims — FastAPI entrypoint.

Reached in prod via nginx route `/claims/` which proxy_passes to this
service on port 8100. Inside the service, API paths are `/api/...` and
the frontend is served at `/`.
"""
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.routers import health, losses, profile

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        os.makedirs(settings.GENERATED_DIR, exist_ok=True)
    except PermissionError:
        logger.warning(
            "GENERATED_DIR=%s not writable; docx generation will fail until "
            "the path is fixed (Phase 4 only).",
            settings.GENERATED_DIR,
        )
    logger.info("uzum-claims started")
    yield


app = FastAPI(title="uzum-claims", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(losses.router, prefix="/api")

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(os.path.join(frontend_path, "index.html"))

    @app.get("/profile", include_in_schema=False)
    async def profile_page():
        return FileResponse(os.path.join(frontend_path, "profile.html"))

    @app.get("/losses", include_in_schema=False)
    async def losses_page():
        return FileResponse(os.path.join(frontend_path, "losses.html"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8100, reload=True)
