from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def readiness() -> dict[str, str]:
    # Day 2 adds dependency probes for PostgreSQL, Redis, Qdrant, and Neo4j.
    return {"status": "ready", "dependencies": "baseline"}
