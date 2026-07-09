"""FastAPI app + Mangum handler.

Runs identically under uvicorn (local dev) and AWS Lambda behind API Gateway
(HTTP API). Mangum's api_gateway_base_path strips the stage prefix (e.g. /prod)
that API Gateway prepends to rawPath.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from api.routes.ai import router as ai_router
from api.routes.auth import router as auth_router
from api.routes.jobs import router as jobs_router
from api.routes.uploads import router as uploads_router

app = FastAPI(title="myapp API", docs_url=None, redoc_url=None)

_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
# Auth uses Bearer headers, not cookies, so credentialed CORS is unnecessary
# (and would be rejected by browsers when combined with a "*" origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(ai_router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": os.environ.get("APP_VERSION", "dev")}


_stage = os.environ.get("STAGE", "")
handler = Mangum(app, lifespan="off", api_gateway_base_path=f"/{_stage}" if _stage else "/")
