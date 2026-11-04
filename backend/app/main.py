import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .core.config import settings
from .services.bharatcode_client import BharatCodeClient, BharatCodeError
from .db import db_ok, init_db
from .routes import router

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clavion")

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info("Clavion API started (model=%s, llm_configured=%s)", settings.bharatcode_model, settings.llm_configured)
    yield


app = FastAPI(title="Clavion API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


class Health(BaseModel):
    status: str
    version: str
    database: bool
    llm_configured: bool
    model: str


class LLMHealth(BaseModel):
    reachable: bool
    model: str
    model_listed: bool
    model_capabilities: dict | None = None
    live_inference: bool | None = None  # None = not attempted
    error: str | None = None


@app.get("/api/health", response_model=Health)
def health() -> Health:
    database = db_ok()
    return Health(
        status="ok" if database else "degraded",
        version=VERSION,
        database=database,
        llm_configured=settings.llm_configured,
        model=settings.bharatcode_model,
    )


@app.get("/api/health/llm", response_model=LLMHealth)
def health_llm(live: bool = False) -> LLMHealth:
    """Checks the BharatCode catalog; with ?live=true also runs one tiny completion (costs tokens)."""
    out = LLMHealth(reachable=False, model=settings.bharatcode_model, model_listed=False)
    client = BharatCodeClient(settings)
    try:
        models = {m["id"]: m for m in client.list_models()}
        out.reachable = True
        if m := models.get(settings.bharatcode_model):
            out.model_listed = True
            out.model_capabilities = m.get("metadata")
    except BharatCodeError as e:
        out.error = f"catalog: {e.kind}"
        log.warning("BharatCode catalog check failed: %s", e.kind)
        return out
    if live:
        try:
            out.live_inference = bool(client.ping())
        except BharatCodeError as e:
            out.live_inference, out.error = False, f"inference: {e.kind}" + (f" ({e.code})" if e.code else "")
    return out
