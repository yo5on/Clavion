"""Claim workflow API: cases, document upload + extraction, manual correction, audit, appeal, PDF export."""

import copy
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Case, get_session
from .demo import fixtures
from .schemas.claim import AppealStatement, AuditReport, DocType, FieldMeta, Provenance
from .services import documents, report as reports
from .services.audit import run_audit
from .services.parsers import PAGE_BREAK, is_synthetic
from .services.providers import PROVIDERS, SCHEMAS, ProviderUnavailable, get_provider

log = logging.getLogger("clavion.routes")
router = APIRouter(prefix="/api")
CaseId = Path(max_length=64)
MAX_TEXT_CHARS = 200_000
MAX_TRAIL = 200


class ProviderInfo(BaseModel):
    id: str
    label: str
    ai: bool
    demo: bool
    status: dict


class CaseCreate(BaseModel):
    title: str = Field(max_length=500)


class AppealUpdate(BaseModel):
    text: str | None = Field(None, max_length=50_000)
    statements: list[AppealStatement] | None = Field(None, max_length=200)


def _provider_info(p) -> ProviderInfo:
    return ProviderInfo(id=p.id, label=p.label, ai=p.ai, demo=p.demo, status=p.status())


def _case(s: Session, case_id: str) -> Case:
    case = s.get(Case, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


def _report(case: Case) -> dict:
    # deep copy: mutating the loaded JSON in place would hide the change from SQLAlchemy
    rep = copy.deepcopy(case.report) or {"demo": False, "documents": {}, "audit": None, "appeal": None}
    rep.setdefault("trail", [])
    return rep


def _event(rep: dict, event: str, detail: str):
    """Audit trail: what was done to the case, when. Never contains document text."""
    rep["trail"] = (rep["trail"] + [{"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "event": event, "detail": detail}])[-MAX_TRAIL:]


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


@router.post("/cases")
def create_case(body: CaseCreate, s: Session = Depends(get_session)):
    title = body.title.strip()[:200] or "Untitled claim"
    case = Case(id=str(uuid.uuid4()), title=title, status="draft", report=None)
    rep = _report(case)
    _event(rep, "case_created", title)
    case.report = rep
    s.add(case)
    s.commit()
    return _out(case)


@router.get("/cases")
def list_cases(s: Session = Depends(get_session)):
    out = []
    for c in s.scalars(select(Case).order_by(Case.created_at.desc())):
        rep = _report(c)
        audit = rep["audit"]
        out.append({"id": c.id, "title": c.title, "status": c.status, "created_at": _created(c),
                    "demo": rep["demo"], "documents": sorted(rep["documents"]),
                    "claimed_amount": audit and audit["claimed_amount"],
                    "approved_amount": audit and audit["approved_amount"],
                    "contestable_total": audit and audit["contestable_total"]})
    return out


@router.get("/cases/{case_id}")
def get_case(case_id: str = CaseId, s: Session = Depends(get_session)):
    return _out(_case(s, case_id))


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: str = CaseId, s: Session = Depends(get_session)):
    """Deletes the case and everything stored for it (extracted text, fields, audit, appeal)."""
    s.delete(_case(s, case_id))
    s.commit()
    return Response(status_code=204)


def _store_document(s: Session, case: Case, doc_type: str, text: str, method: str, warnings: list[str],
                    filename: str, provider_id: str, sha256: str | None = None) -> dict:
    try:
        provider = get_provider(provider_id)
        doc, parse_warnings, fields = provider.extract(doc_type, text)
    except ProviderUnavailable as e:
        raise HTTPException(409, str(e)) from None
    except Exception as e:  # a parser bug must not lose the upload silently or leak a stack trace
        log.exception("extraction failed for %s", doc_type)
        raise HTTPException(422, f"the {doc_type} could not be interpreted ({type(e).__name__}); "
                                 f"try a clearer copy or a text-based PDF") from None
    guessed = documents.guess_type(text)
    if guessed and guessed != doc_type:
        warnings = warnings + [f"this file reads like a {reports.DOC_LABELS[guessed].lower()}, not a "
                               f"{reports.DOC_LABELS[doc_type].lower()}; check it was uploaded in the right place"]
    prov = Provenance(provider=provider.id, label=provider.label, ai_generated=provider.ai,
                      demo=provider.demo or is_synthetic(text), text_method=method,
                      pages=text.count(PAGE_BREAK) + 1, sha256=sha256, warnings=warnings + parse_warnings)
    rep = _report(case)
    rep["documents"] = {**rep["documents"], doc_type: {
        "data": doc.model_dump(mode="json"), "provenance": prov.model_dump(), "text": text[:MAX_TEXT_CHARS],
        "filename": filename[:200], "fields": {k: v.model_dump(mode="json") for k, v in fields.items()}}}
    rep["audit"] = rep["appeal"] = None  # inputs changed: the old audit no longer applies
    _event(rep, "document_uploaded", f"{reports.DOC_LABELS[doc_type]}: {filename[:200]} ({method}, "
                                     f"{prov.pages} page(s), {len(prov.warnings)} warning(s))")
    return _save(s, case, rep, "draft")


@router.post("/cases/{case_id}/documents/{doc_type}")
def upload_document(doc_type: DocType, case_id: str = CaseId, file: UploadFile = File(...),
                    provider: str = Form("local", max_length=20), s: Session = Depends(get_session)):
    case = _case(s, case_id)
    data = file.file.read(documents.MAX_UPLOAD_BYTES + 1)
    name = (file.filename or doc_type).replace("\\", "/").rsplit("/", 1)[-1]  # never keep a client path
    digest = hashlib.sha256(data).hexdigest()
    for other, d in _report(case)["documents"].items():
        if other != doc_type and d["provenance"].get("sha256") == digest:
            raise HTTPException(409, f"this file is already uploaded as the {reports.DOC_LABELS[other].lower()}")
    try:
        text, method, warnings = documents.extract_text(name, data)
    except documents.DocumentError as e:
        raise HTTPException(422, str(e)) from None
    if not text.strip():
        raise HTTPException(422, "no text could be read from this file")
    return _store_document(s, case, doc_type, text, method, warnings, name, provider, digest)


def _remap_fields(old_data: dict, new_data: dict, fields: dict) -> dict:
    """Field statuses after a manual correction: changed values become 'corrected' (keeping their source), list
    items that only moved keep their status, and new items are 'corrected' with no source."""
    out = {}
    for key, new in new_data.items():
        old = old_data.get(key)
        if isinstance(new, list) and new and isinstance(new[0], dict):
            used: set[int] = set()
            for i, item in enumerate(new):
                j = next((j for j, o in enumerate(old or []) if j not in used and o == item), None)
                if j is not None:
                    used.add(j)
                    for p, m in fields.items():  # carry the item and its sub-fields over to the new index
                        if p == f"{key}.{j}" or p.startswith(f"{key}.{j}."):
                            out[f"{key}.{i}" + p[len(f"{key}.{j}"):]] = m
                else:
                    src = fields.get(f"{key}.{i}", {}).get("source") if i < len(old or []) else None
                    out[f"{key}.{i}"] = FieldMeta(status="corrected", source=src,
                                                  note="edited on the review screen" if src else
                                                  "added on the review screen").model_dump(mode="json")
        elif new != old:
            src = fields.get(key, {}).get("source")
            out[key] = FieldMeta(status="corrected", source=src, note=f"was {old!r}" if old not in (None, [], "")
                                 else "entered on the review screen").model_dump(mode="json")
        elif key in fields:
            out[key] = fields[key]
    return out


@router.put("/cases/{case_id}/documents/{doc_type}")
def correct_document(doc_type: DocType, body: dict, case_id: str = CaseId, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if doc_type not in rep["documents"]:
        raise HTTPException(404, "upload this document first")
    try:
        doc = SCHEMAS[doc_type].model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    entry = rep["documents"][doc_type]
    new_data = doc.model_dump(mode="json")
    fields = _remap_fields(entry["data"], new_data, entry.get("fields", {}))
    changed = sorted({k.split(".")[0] for k, v in fields.items() if v["status"] == "corrected"})
    rep["documents"] = {**rep["documents"], doc_type: {
        **entry, "data": new_data, "fields": fields, "provenance": {**entry["provenance"], "manually_corrected": True}}}
    rep["audit"] = rep["appeal"] = None
    _event(rep, "document_corrected", f"{reports.DOC_LABELS[doc_type]}: "
                                      f"{', '.join(changed) or 'saved without changes'}")
    return _save(s, case, rep, "draft")


def _sources(rep: dict) -> tuple[dict, dict, dict]:
    docs = rep["documents"]
    sources = {t: {k: FieldMeta.model_validate(v) for k, v in d.get("fields", {}).items()} for t, d in docs.items()}
    filenames = {t: d["filename"] for t, d in docs.items()}
    info = {t: {"warnings": d["provenance"]["warnings"], "manually_corrected": d["provenance"]["manually_corrected"]}
            for t, d in docs.items()}
    return sources, filenames, info


@router.post("/cases/{case_id}/audit")
def audit_case(case_id: str = CaseId, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if "settlement" not in rep["documents"]:
        raise HTTPException(409, "upload the settlement letter first: it lists the deductions to audit")
    settlement = _doc(rep, "settlement")
    bill = _doc(rep, "bill")
    sources, filenames, info = _sources(rep)
    result = run_audit(bill, _doc(rep, "policy"), settlement, demo=rep["demo"], sources=sources,
                       filenames=filenames, doc_info=info)
    rep["audit"] = result.model_dump(mode="json")
    statements = reports.appeal_statements(result, settlement, bill.patient_name if bill else None)
    rep["appeal"] = {"text": reports.compose(statements), "statements": [x.model_dump() for x in statements],
                     "source": reports.APPEAL_SOURCE, "edited": False}
    _event(rep, "audit_run", f"rules {result.rules_version}: {len(result.findings)} finding(s), contestable "
                             f"Rs {result.contestable_total:,.2f}, needs clarification Rs {result.unverified_total:,.2f}")
    return _save(s, case, rep, "audited")


@router.put("/cases/{case_id}/appeal")
def update_appeal(body: AppealUpdate, case_id: str = CaseId, s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if not rep["appeal"]:
        raise HTTPException(409, "run the audit first")
    if body.statements is not None:
        text, statements = reports.compose(body.statements), [x.model_dump() for x in body.statements]
    elif body.text is not None:
        text, statements = body.text, []  # free text replaces the statement list
    else:
        raise HTTPException(422, "send the letter text or its statements")
    rep["appeal"] = {**rep["appeal"], "text": text, "statements": statements, "edited": True}
    edited = sum(1 for x in statements if x["edited"])
    _event(rep, "appeal_saved", f"{edited} statement(s) edited, "
                                f"{sum(1 for x in statements if not x['include'])} left out" if statements
           else "free-text letter saved")
    return _save(s, case, rep)


@router.get("/cases/{case_id}/export.pdf")
def export_pdf(case_id: str = CaseId, kind: Literal["report", "appeal"] = "report", s: Session = Depends(get_session)):
    case = _case(s, case_id)
    rep = _report(case)
    if not rep["audit"]:
        raise HTTPException(409, "run the audit first")
    pdf = reports.build_pdf(kind, case.title, AuditReport.model_validate(rep["audit"]),
                            rep["appeal"]["text"] if rep["appeal"] else None)
    name = f"clavion-{kind}-{case.id[:8]}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                                "Cache-Control": "no-store"})


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
