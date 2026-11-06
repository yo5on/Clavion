import logging
from contextlib import asynccontextmanager
from importlib.util import find_spec

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .core.config import settings
from .db import db_ok, init_db
from .routes import router
from .services.audit import METHOD

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clavion")

VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info("Clavion API %s started: local-first, no external services", VERSION)
    yield


app = FastAPI(title="Clavion API", version=VERSION, lifespan=lifespan,
              description="Local-first insurance claim auditing: PDF text extraction, offline OCR, rule-based "
                          "parsing and Decimal calculations. No external or AI services are called.")
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
    ocr_available: bool  # offline OCR engine installed (needed for images and scanned PDFs)
    analysis: str  # how audits are computed; always local rules


@app.get("/api/health", response_model=Health)
def health() -> Health:
    database = db_ok()
    return Health(status="ok" if database else "degraded", version=VERSION, database=database,
                  ocr_available=find_spec("rapidocr_onnxruntime") is not None, analysis=METHOD)
