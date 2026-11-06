"""Extraction providers: plain text -> structured document. Both run locally; neither calls any external service.

- local  deterministic rule-based parsers in services/parsers.py (default)
- demo   pre-labelled ground truth for Clavion's own synthetic fixtures only

Providers only structure text. Money arithmetic and audit conclusions are always done by services/audit.py, so no
provider can produce a calculation result.
"""

from pydantic import BaseModel

from ..schemas.bill import HospitalBill
from ..schemas.claim import DocType, FieldMeta, PolicyDocument, SettlementLetter
from . import parsers

SCHEMAS: dict[str, type[BaseModel]] = {"bill": HospitalBill, "policy": PolicyDocument, "settlement": SettlementLetter}


class ProviderUnavailable(RuntimeError):
    pass


class LocalProvider:
    id, label, ai, demo = "local", "Local deterministic parser", False, False

    def status(self) -> dict:
        return {"state": "available", "detail": "Rule-based parsing on this server. No AI inference."}

    def extract(self, doc_type: DocType, text: str) -> tuple[BaseModel, list[str], dict[str, FieldMeta]]:
        x = parsers.EXTRACTORS[doc_type](text)
        return x.doc, x.warnings, x.fields


class DemoProvider:
    id, label, ai, demo = "demo", "Demo fixture (synthetic ground truth)", False, True

    def status(self) -> dict:
        return {"state": "available", "detail": "Returns pre-labelled answers for Clavion's synthetic documents only."}

    def extract(self, doc_type: DocType, text: str) -> tuple[BaseModel, list[str], dict[str, FieldMeta]]:
        from ..demo import fixtures

        if fixtures.FIXTURE_ID not in text:
            raise ProviderUnavailable("the demo provider only handles Clavion's synthetic demo documents")
        # Pre-labelled values have no source location: they were not read from the text.
        return fixtures.ground_truth(doc_type), ["demo fixture: values are pre-labelled, not extracted"], {}


PROVIDERS = {p.id: p for p in (LocalProvider(), DemoProvider())}


def get_provider(provider_id: str):
    if provider_id not in PROVIDERS:
        raise ProviderUnavailable(f"unknown provider '{provider_id}'")
    return PROVIDERS[provider_id]
