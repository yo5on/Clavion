import logging
from contextlib import asynccontextmanager
from importlib.util import find_spec

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .core.config import settings
from .auth import OwnerAccessMiddleware, router as auth_router
from .db import db_ok, init_db
from .routes import router
from .services.audit import METHOD

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clavion")

VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.auth_enabled:
        log.warning("Authentication disabled: use only on a trusted loopback interface")
    log.info("Clavion API %s started: local-first, no external services", VERSION)
    yield


class Health(BaseModel):
    status: str
    version: str
    database: bool
    ocr_available: bool  # offline OCR engine installed (needed for images and scanned PDFs)
    analysis: str  # how audits are computed; always local rules


def health() -> Health:
    database = db_ok()
    return Health(status="ok" if database else "degraded", version=VERSION, database=database,
                  ocr_available=find_spec("rapidocr_onnxruntime") is not None, analysis=METHOD)


def create_app() -> FastAPI:
    app = FastAPI(title="Clavion API", version=VERSION, lifespan=lifespan,
                  description="Local-first insurance claim auditing: PDF text extraction, offline OCR, rule-based "
                              "parsing and Decimal calculations. No external or AI services are called.")
    app.add_middleware(OwnerAccessMiddleware)
    # CORS wraps the access gate so allowed clients can read authentication errors.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    app.include_router(auth_router)
    app.include_router(router)
    app.add_api_route("/api/health", health, response_model=Health)
    return app


app = create_app()
