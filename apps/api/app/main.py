from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.api.routes import banking, health, investigations, security, transactions
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.observability import configure_observability

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Multi-agent banking risk, fraud, AML, and credit intelligence API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(transactions.router)
app.include_router(investigations.router)
app.include_router(security.router)
app.include_router(banking.router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "operational", "docs": "/docs"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Production observability
configure_observability(app)
