# CLAVION — Insurance Claims Intelligence

> Every deduction deserves an explanation.

Clavion audits Indian health insurance claim settlements. You upload the hospital bill, the policy wording and the
insurer's settlement letter. Clavion reads them locally, recalculates every deduction with exact decimal arithmetic,
shows the clause and bill lines each conclusion rests on, and drafts an appeal you can edit statement by statement.

**Local-first, no AI APIs.** Text extraction (pypdf, RapidOCR on ONNX), parsing, rules and PDF generation all run on
your machine. No document, field or result is sent to any external service. There is no model inference anywhere
in the pipeline: every conclusion comes from a named rule you can read in `backend/app/services/rules.py`.

Clavion never says a deduction is illegal, unlawful or guaranteed to be recoverable. A finding is either
**supported** by the documents, **potentially contestable** (the documents do not support part of it), or
**needs clarification** (the documents cannot decide, and Clavion says what is missing).

See [`docs/PRODUCT_AUDIT.md`](docs/PRODUCT_AUDIT.md) for the critical product review behind this version, its
priorities and its known limitations.

## How an audit works

1. **Upload** (PDF, PNG/JPG/TIFF/WEBP/BMP, or UTF-8 text). The file signature must match the extension; size,
   page count and image pixel count are bounded; encrypted and malformed PDFs are rejected with a clear message.
   PDFs use their text layer, and pages with too little text are OCR'd. Low OCR confidence is reported. Uploading
   the same file into two slots is refused, and a file that reads like the wrong document type is flagged.
2. **Extract** with deterministic parsers. Every field carries a status — *extracted*, *inferred*, *missing* or
   *corrected* — and, where it came from the document, its page, line and the original text.
3. **Review**. Each field shows where it was read ("Read from p. 2, line 14"). Corrections are validated and
   marked *corrected*, keeping the original source for comparison.
4. **Audit** (`services/rules.py`, `services/audit.py`). Each deduction is classified and run through one rule.
   Every finding answers eight questions: what happened, the amount, what the insurer stated, the policy clause,
   the evidence, why it may be contestable, what is missing, and the next step. It also lists the rule's
   conditions (met / not met / could not be checked). Consistency checks then cross-check the three documents.
5. **Appeal**. The letter is built from typed statements: *from your documents* (source facts with page/line
   references), *Clavion calculation*, *suggested wording* and *letter formality*. Each can be edited or left out.
   Report and letter export to PDF (`Cache-Control: no-store`).

### Rules (version 2026.11-1)

| Rule | What it recalculates | Needs |
|---|---|---|
| R-ROOM-01 | Room rent above the daily limit, **line by line** (mixed room rates are not averaged) | room-rent limit, room lines with days |
| R-ICU-01 | ICU above the daily limit, line by line | ICU limit, ICU lines with days |
| R-PROP-01 | Proportionate deduction on associated charges, excluding categories the policy exempts. If the insurer's figure is higher, Clavion searches the exempt categories for the exact combination that reproduces it and names them | proportionate clause, room limit, a single room rate |
| R-COPAY-01 | Co-pay % on the claim after other deductions; detects co-pay applied to the gross claim | co-pay %, claimed amount |
| R-SUBLIMIT-01 | Amount above a treatment sub-limit | sub-limits, matching bill lines |
| R-EXCL-01 | Item on the policy's exclusions list | exclusions clause, matching bill line |
| R-NONPAY-01 | Item on the policy's non-payable list | non-payable clause, matching bill line |
| R-UNSPEC-01 | No reason given: always *needs clarification* | — |
| R-REC-01 | Gap between claimed − approved and the listed deductions | claimed, approved |

Differences up to Rs 1.00 are treated as rounding. A room-category limit ("single private room") cannot be turned
into rupees, so such deductions stay *needs clarification* and Clavion asks for the eligible room rent.

### Consistency checks

Settlement arithmetic (C-REC-01/02), bill arithmetic (C-REC-03/04), claim vs bill total (C-REC-05), paid vs approved
(C-REC-06), duplicate bill lines and deductions (C-DUP-01/02), deductions exceeding what was billed (C-OVL-01), room
days vs length of stay (C-STAY-01), cited clauses present in the policy (C-CIT-01), policy number / patient /
hospital consistency (C-ID-01..03), approved within sum insured (C-SI-01), unreviewed extraction warnings
(C-DOC-01). A check whose inputs are missing is reported as *not checked*, never as passed.

## Architecture

```
frontend/  React 19 + TypeScript + Vite + Tailwind v4 + lucide-react
  src/api.ts                    typed client (mirrors backend Pydantic models)
  src/components/AuditView.tsx  totals, findings (eight parts + rule trace), reconciliation, checks, readiness
  src/components/DocumentViewer.tsx  page/line view of the extracted text, target line highlighted
  src/components/ReviewForms.tsx     field editors with per-field status and source
  src/pages/CaseView.tsx        review / audit / appeal (statement editor), audit trail, delete case
backend/   Python + FastAPI + Pydantic + SQLAlchemy (SQLite)
  app/services/documents.py     file validation, PDF text, local OCR, document-type guess
  app/services/parsers.py       bill / policy / settlement extraction with per-field provenance
  app/services/rules.py         rule registry, rule evaluation, consistency checks
  app/services/audit.py         findings, totals, readiness, documents to request
  app/services/calculations.py  Decimal money maths
  app/services/report.py        appeal statements, letter composition, PDF export
  app/services/providers.py     local parser | demo (ground truth for Clavion's own synthetic fixtures only)
  app/demo/fixtures.py          SYNTHETIC demo case with hand-computed expected results
  app/routes.py                 cases, documents, audit, appeal, export, delete, audit trail
  tests/                        pytest: rules, parsers, security, synthetic end-to-end cases
  scripts/render_synthetic_cases.py  writes the synthetic test documents as PDFs for manual testing
```

## Setup

Requirements: Python 3.11+, Node 20+.

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Try it without documents: **Try the synthetic demo** on the dashboard, or download the synthetic PDFs/images from
the New audit page and upload them. Everything derived from synthetic documents is labelled DEMO.

## Tests

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm run lint
```

146 backend tests. Highlights:

- `tests/synthetic_cases.py` — nine synthetic claims (simple, room rent + proportionate, co-pay, sub-limit and
  non-payable, missing clauses, poor OCR scan, exclusions, two-page bill with "/-" amounts and rounding, conflicting
  documents with a table-format letter). Each is rendered to PDF (or a degraded scan), read back, parsed and
  audited; every amount is compared with a hand calculation written in the comments.
- `tests/test_rules.py` — each rule and check in isolation, including mixed room rates, the rounding boundary,
  co-pay on the gross claim, subset reproduction of a proportionate figure, and readiness states.
- `tests/test_document_intelligence.py` — page/line provenance across pages, field statuses, table-format
  letters, deduction lines without amounts, dates, room-category policies.
- `tests/test_security.py` — signature mismatch, malformed and encrypted PDFs, decompression bomb, size limit,
  duplicate upload, client path stripping, case isolation and deletion, audit trail without document text,
  appeal statement editing and export.

## Privacy and security

- No external calls. No API keys. Uploaded files are processed in memory and never written to disk; only the
  extracted text and fields are stored, in the local SQLite database (`secure_delete` on).
- Deleting a case removes its text, fields, audit and appeal.
- The audit trail records events (uploads, corrections, audits, appeal saves) but never document text or amounts.
- Uploads: 15 MB, 60 PDF pages, 40 megapixels per image; signature checked; client paths stripped from file names.
- There is no authentication: run Clavion on your own machine, not as a shared server.
