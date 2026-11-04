"""Claim workflow API: cases, document upload + extraction, manual correction, audit, appeal, PDF export."""

import copy
import uuid
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Case, get_session
from .demo import fixtures
from .schemas.claim import AuditReport, DocType, Provenance
from .services import documents, report as reports
from .services.audit import run_audit
from .services.parsers import SYNTHETIC_MARKER
from .services.providers import PROVIDERS, SCHEMAS, ProviderUnavailable, get_provider

router = APIRouter(prefix="/api")


class ProviderInfo(BaseModel):
    id: str
    label: str
    ai: bool
    demo: bool
    status: dict


class CaseCreate(BaseModel):
    title: str


class AppealUpdate(BaseModel):
    text: str


def _provider_info(p) -> ProviderInfo:
    return ProviderInfo(id=p.id, label=p.label, ai=p.ai, demo=p.demo, status=p.status())


def _case(s: Session, case_id: str) -> Case:
    case = s.get(Case, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


def _report(case: Case) -> dict:
    # deep copy: mutating the loaded JSON in place would hide the change from SQLAlchemy
    return copy.deepcopy(case.report) or {"demo": False, "documents": {}, "audit": None, "appeal": None}


def _save(s: Session, case: Case, rep: dict, status: str | None = None) -> dict:
    rep["demo"] = any(d["provenance"]["demo"] for d in rep["documents"].values())
    case.report = rep
    if status:
        case.status = status
    s.commit()
    return _out(case)


def _created(case: Case) -> str:
    # SQLite drops the timezone; values are stored in UTC
    return case.created_at.replace(tzinfo=case.created_at.tzinfo or timezone.utc).isoformat()


def _out(case: Case) -> dict:
    return {"id": case.id, "title": case.title, "status": case.status, "created_at": _created(case), **_report(case)}


def _doc(rep: dict, doc_type: str):
    d = rep["documents"].get(doc_type)
    return SCHEMAS[doc_type].model_validate(d["data"]) if d else None


@router.get("/providers", response_model=list[ProviderInfo])
def providers():
    return [_provider_info(p) for p in PROVIDERS.values()]


@router.post("/providers/bharatcode/check", response_model=ProviderInfo)
def check_bharatcode():
    PROVIDERS["bharatcode"].check()
    return _provider_info(PROVIDERS["bharatcode"])


@router.post("/cases")
def create_case(body: CaseCreate, s: Session = Depends(get_session)):
    title = body.title.strip()[:200] or "Untitled claim"
    case = Case(id=str(uuid.uuid4()), title=title, status="draft", report=None)
    s.add(case)
    s.commit()
    return _out(case)


@router.get("/cases")
def list_cases(s: Session = Depends(get_session)):
    out = []
    for c in s.scalars(select(Case).order_by(Case.created_at.desc())):
        rep, audit = _report(c), _report(c)["audit"]
        out.append({"id": c.id, "title": c.title, "status": c.status, "created_at": _created(c),
                    "demo": rep["demo"], "documents": sorted(rep["documents"]),
                    "claimed_amount": audit and audit["claimed_amount"],
                    "approved_amount": audit and audit["approved_amount"],
                    "contestable_total": audit and audit["contestable_total"]})
    return out


@router.get("/cases/{case_id}")
def get_case(case_id: str, s: Session = Depends(get_session)):
    return _out(_case(s, case_id))


def _store_document(s: Session, case: Case, doc_type: str, text: str, method: str, warnings: list[str],
                    filename: str, provider_id: str) -> dict:
    try:
        provider = get_provider(provider_id)
        doc, parse_warnings = provider.extract(doc_type, text)
    except ProviderUnavailable as e:
        raise HTTPException(409, str(e)) from None
    prov = Provenance(provider=provider.id, label=provider.label, ai_generated=provider.ai,
                      demo=provider.demo or SYNTHETIC_MARKER in text, text_method=method,
                      warnings=warnings + parse_warnings)
    rep = _report(case)
    rep["documents"] = {**rep["documents"], doc_type: {"data": doc.model_dump(mode="json"),
                                                       "provenance": prov.model_dump(), "text": text[:200_000],
                                                       "filename": filename}}
    rep["audit"] = rep["appeal"] = None  # inputs changed: the old audit no longer applies
    return _save(s, case, rep, "draft")


@router.post("/cases/{case_id}/documents/{doc_type}")
def upload_document(case_id: str, doc_type: DocType, file: UploadFile = File(...), provider: str = Form("local"),
                    s: Session = Depends(get_session)):
    case = _case(s, case_id)
    data = file.file.read(documents.MAX_UPLOAD_BYTES + 1)
    try:
        text, method, warnings = documents.extract_text(file.filename or "", data)
    except documents.DocumentError as e:
        raise HTTPException(422, str(e)) from None
    if not text.strip():
        raise HTTPException(422, "no text could be read from this file")
    return _store_document(s, case, doc_type, text, method, warnings, file.filename or doc_type, provider)


@router.put("/cases/{case_id}/documents/{doc_type}")
def correct_document(case_id: str, doc_type: DocType, body: dict, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if doc_type not in rep["documents"]:
        raise HTTPException(404, "upload this document first")
    try:
        doc = SCHEMAS[doc_type].model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    entry = rep["documents"][doc_type]
    rep["documents"] = {**rep["documents"], doc_type: {
        **entry, "data": doc.model_dump(mode="json"), "provenance": {**entry["provenance"], "manually_corrected": True}}}
    rep["audit"] = rep["appeal"] = None
    return _save(s, case, rep, "draft")


@router.post("/cases/{case_id}/audit")
def audit_case(case_id: str, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if "settlement" not in rep["documents"]:
        raise HTTPException(409, "upload the settlement letter first: it lists the deductions to audit")
    settlement = _doc(rep, "settlement")
    bill = _doc(rep, "bill")
    result = run_audit(bill, _doc(rep, "policy"), settlement, demo=rep["demo"])
    rep["audit"] = result.model_dump(mode="json")
    rep["appeal"] = {"text": reports.appeal_letter(result, settlement, bill.patient_name if bill else None),
                     "source": "Local template filled from audit findings (no AI)", "edited": False}
    return _save(s, case, rep, "audited")


@router.put("/cases/{case_id}/appeal")
def update_appeal(case_id: str, body: AppealUpdate, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if not rep["appeal"]:
        raise HTTPException(409, "run the audit first")
    rep["appeal"] = {**rep["appeal"], "text": body.text[:50_000], "edited": True}
    return _save(s, case, rep)


@router.get("/cases/{case_id}/export.pdf")
def export_pdf(case_id: str, kind: Literal["report", "appeal"] = "report", s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if not rep["audit"]:
        raise HTTPException(409, "run the audit first")
    pdf = reports.build_pdf(kind, case.title, AuditReport.model_validate(rep["audit"]),
                            rep["appeal"]["text"] if rep["appeal"] else None)
    name = f"clavion-{kind}-{case.id[:8]}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/demo/case")
def demo_case(s: Session = Depends(get_session)):
    """Creates a case from the SYNTHETIC fixtures, parsed by the real local parser, then audits it."""
    case = Case(id=str(uuid.uuid4()), title="DEMO - Synthetic appendectomy claim", status="draft", report=None)
    s.add(case)
    s.commit()
    for doc_type, text in fixtures.TEXTS.items():
        _store_document(s, case, doc_type, text, "plain-text", [], f"synthetic-{doc_type}.txt", "local")
    return audit_case(case.id, s)


@router.get("/demo/documents/{doc_type}")
def demo_document(doc_type: DocType, format: Literal["pdf", "png"] = "pdf"):
    text = fixtures.TEXTS[doc_type]
    data = fixtures.render_pdf(text) if format == "pdf" else fixtures.render_png(text)
    return Response(data, media_type="application/pdf" if format == "pdf" else "image/png",
                    headers={"Content-Disposition": f'attachment; filename="synthetic-{doc_type}.{format}"'})
