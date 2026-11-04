"""Extraction providers: plain text -> structured document.

- local       deterministic parsers in services/parsers.py (default, always available)
- demo        pre-labelled ground truth for Clavion's own synthetic fixtures only
- bharatcode  BharatCode model via the existing client; enabled only after a live inference check succeeds

Providers only structure text. Money arithmetic and audit conclusions are always done by services/audit.py, so no
provider (model or fixture) can produce a calculation result.
"""

import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from ..core.config import BACKEND_DIR, settings
from ..schemas.bill import EXTRACTION_INSTRUCTIONS, HospitalBill
from ..schemas.claim import DocType, PolicyDocument, SettlementLetter
from . import parsers
from .bharatcode_client import BharatCodeClient, BharatCodeError

log = logging.getLogger("clavion.providers")

SCHEMAS: dict[str, type[BaseModel]] = {"bill": HospitalBill, "policy": PolicyDocument, "settlement": SettlementLetter}
STATUS_FILE = BACKEND_DIR / ".provider_status.json"  # git-ignored; holds only the last check's state, no secrets
MIN_CHECK_INTERVAL_S = 60  # never hit a blocked endpoint more than once a minute, however often the button is pressed


class ProviderUnavailable(RuntimeError):
    pass


class LocalProvider:
    id, label, ai, demo = "local", "Local deterministic parser", False, False

    def status(self) -> dict:
        return {"state": "available", "detail": "Rule-based parsing on this server. No AI inference."}

    def extract(self, doc_type: DocType, text: str) -> tuple[BaseModel, list[str]]:
        return {"bill": parsers.parse_bill, "policy": parsers.parse_policy,
                "settlement": parsers.parse_settlement}[doc_type](text)


class DemoProvider:
    id, label, ai, demo = "demo", "Demo fixture (synthetic ground truth)", False, True

    def status(self) -> dict:
        return {"state": "available", "detail": "Returns pre-labelled answers for Clavion's synthetic documents only."}

    def extract(self, doc_type: DocType, text: str) -> tuple[BaseModel, list[str]]:
        from ..demo import fixtures

        if fixtures.FIXTURE_ID not in text:
            raise ProviderUnavailable("the demo provider only handles Clavion's synthetic demo documents")
        return fixtures.ground_truth(doc_type), ["demo fixture: values are pre-labelled, not extracted"]


class BharatCodeProvider:
    id, ai, demo = "bharatcode", True, False

    @property
    def label(self) -> str:
        return f"BharatCode ({settings.bharatcode_model})"

    def status(self) -> dict:
        if not settings.llm_configured:
            return {"state": "not_configured", "detail": "BHARATCODE_API_KEY is not set."}
        try:
            saved = json.loads(STATUS_FILE.read_text())
        except (OSError, ValueError):
            return {"state": "not_checked", "detail": "Connection has not been checked yet."}
        return saved

    def check(self) -> dict:
        """One live inference call; the only place Clavion decides whether BharatCode is connected."""
        current = self.status()
        if current["state"] == "not_configured":
            return current
        if checked := current.get("checked_at"):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds()
            if age < MIN_CHECK_INTERVAL_S:
                return current
        try:
            BharatCodeClient(settings).ping()
            state, detail = "connected", "Live inference succeeded."
        except BharatCodeError as e:
            if e.code == "subscription_required":
                state, detail = "subscription_required", "Key recognised, but the account has no API plan (HTTP 402)."
            else:
                state, detail = "connection_failed", f"{e.kind}" + (f" ({e.code})" if e.code else "")
        out = {"state": state, "detail": detail, "checked_at": datetime.now(timezone.utc).isoformat(),
               "model": settings.bharatcode_model}
        STATUS_FILE.write_text(json.dumps(out))
        log.info("BharatCode check: %s", state)
        return out

    def extract(self, doc_type: DocType, text: str) -> tuple[BaseModel, list[str]]:
        if self.status()["state"] != "connected":
            raise ProviderUnavailable("BharatCode is not connected; use the local parser")
        schema = SCHEMAS[doc_type]
        instructions = EXTRACTION_INSTRUCTIONS if doc_type == "bill" else (
            f"Extract the document into one JSON object matching this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}\nCopy values exactly as printed. Use null for anything not "
            f"present. Do not compute or correct amounts. Return only the JSON object.")
        try:
            doc, _ = BharatCodeClient(settings).chat_json(
                [{"role": "system", "content": instructions}, {"role": "user", "content": text}], schema)
        except BharatCodeError as e:
            raise ProviderUnavailable(f"BharatCode extraction failed: {e.kind}") from None
        return doc, ["extracted by an AI model: check every value against the document"]


PROVIDERS = {p.id: p for p in (LocalProvider(), BharatCodeProvider(), DemoProvider())}


def get_provider(provider_id: str):
    if provider_id not in PROVIDERS:
        raise ProviderUnavailable(f"unknown provider '{provider_id}'")
    return PROVIDERS[provider_id]
