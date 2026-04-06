"""
FastAPI application entry point.

Structure:
  main.py             — app setup, middleware, router mounting
  api/v1/routes/      — HTTP endpoints (thin, no business logic)
  services/           — business logic
  repositories/       — all DB queries
  models/             — SQLAlchemy ORM (DB tables)
  schemas/            — Pydantic (request/response shapes)
  workers/            — Celery async jobs
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import matches, predictions, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup and once on shutdown.
    Good place for: DB connection warmup, cache pre-loading, etc.
    """
    # TODO Phase 2: kick off background cache warm here
    yield
    # TODO Phase 7: graceful shutdown hooks


app = FastAPI(
    title="Parlay Beater API",
    version="1.0.0",
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# All routes versioned under /api/v1/
app.include_router(matches.router,     prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1")
app.include_router(teams.router,       prefix="/api/v1")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": "1.0.0"}
