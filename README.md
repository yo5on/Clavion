# CLAVION — Insurance Claims Intelligence

> Every deduction deserves an explanation.

Clavion audits Indian health insurance claim settlements. You upload a hospital bill, the policy document and the
insurer's settlement letter. Clavion finds deductions that may be contestable, cites the policy clause behind each
one, computes amounts in deterministic Python, and drafts an evidence-backed appeal.

Clavion never says a deduction is illegal or guaranteed to be recoverable. When evidence is missing, it says so.

Built for **BharatCode Build League 2026** on the [BharatCode API](https://bharatcode.ai/build). See
[`BharatCode.txt`](BharatCode.txt) for the integration details and what has been verified live.

## Status

| Phase | Scope | State |
|---|---|---|
| 1. Foundation | FastAPI + SQLite, BharatCode client, health checks, React shell | **Done** |
| 2. Document intelligence | Upload, PDF text + local OCR, deterministic parsers, review and manual correction | **Done (local)** |
| 3. Claim auditing | Clause retrieval, deduction analysis, Decimal calculations, evidence links | **Done (local rules)** |
| 4. Product experience | Dashboard, findings, evidence viewer, appeal letter, PDF export, case history | **Done** |
| 5. Reliability | Synthetic eval set, end-to-end tests | Partly done (synthetic only; no real-document eval yet) |
| BharatCode inference | Hackathon API requirement | **Not met**: key recognised, HTTP 402 `subscription_required` |

Everything runs locally without paid API access. The BharatCode integration is kept intact behind a provider
interface and is enabled only after a live inference check succeeds. No result is ever labelled as BharatCode
inference unless BharatCode produced it.

## How an audit works

1. **Upload** bill, policy and settlement letter (PDF, image or text). PDFs use their text layer (pypdf); images and
   scanned pages use local OCR (RapidOCR, ONNX, offline). Files are processed in memory and not stored.
2. **Extract** with a provider: `local` (deterministic parsers, default), `demo` (ground truth for Clavion's own
   synthetic fixtures only) or `bharatcode` (disabled until connected). Output is validated by Pydantic.
3. **Review** every extracted field; corrections are validated and marked "manually corrected".
4. **Audit** (`services/audit.py`): each settlement deduction is classified (room rent, ICU, proportionate,
   non-payable, sub-limit, co-pay, unspecified), recalculated with `Decimal` from the bill and policy, and linked to
   the clause and bill lines it rests on. Each finding is **supported**, **potentially contestable** (the documents
   do not support part of it) or **unverified** (the documents cannot decide). Missing or inconsistent information
   is listed.
5. **Appeal letter** drafted from the findings by a local template, editable; audit report and letter export to PDF.

## Architecture

```
frontend/  React 19 + TypeScript + Vite + Tailwind v4 + lucide-react
  src/api.ts            typed API client (mirrors backend Pydantic models)
  src/components/       Layout, Logo, ui kit, ProviderStatus, ReviewForms, AuditView (+ evidence viewer)
  src/pages/            Dashboard, NewAudit, CaseView (review / audit / appeal), Cases
backend/   Python + FastAPI + Pydantic + SQLAlchemy (SQLite)
  app/core/config.py    settings from env / .env (key held as SecretStr)
  app/services/bharatcode_client.py   BharatCode client: auth, timeouts, retries, error classification
  app/services/calculations.py        deterministic money maths
  app/schemas/bill.py   bill extraction schema + Python arithmetic checks
  app/schemas/claim.py  settlement, policy, provenance, finding and audit report schemas
  app/services/documents.py       PDF text + local OCR
  app/services/parsers.py         deterministic bill / policy / settlement parsers
  app/services/providers.py       local | demo | bharatcode providers + BharatCode status check
  app/services/policy_analysis.py clause search (keyword BM25)
  app/services/audit.py           audit engine: findings, evidence, missing information
  app/services/report.py          appeal letter template, PDF export
  app/demo/fixtures.py            SYNTHETIC demo case with hand-computed expected results
  app/routes.py         /api/cases, documents, audit, appeal, export.pdf, /api/providers, /api/demo
  app/db.py             engine, Case model (stores extracted results, not uploaded files)
  app/main.py           app, CORS, /api/health, /api/health/llm
  scripts/test_*.py     live capability tests (auth, inference, JSON, image, tools) on a SYNTHETIC bill
  tests/                pytest
```

The Vite dev server proxies `/api` to `localhost:8000`, so the browser never sees the API key.

Providers only turn text into structured fields. All money arithmetic and every audit conclusion is computed in
Python; no model or fixture can supply a calculated result.

## Setup

Requirements: Python 3.11+, Node 20+.

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env  # then set BHARATCODE_API_KEY (repo-root .env or backend/.env)
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Check the BharatCode integration against the live API:

```bash
cd backend
python scripts/test_bharatcode.py --all-models
python scripts/test_image_input.py --all-models
python scripts/test_tool_calling.py --all-models
```

API calls need a BharatCode Lite, Pro or verified-student plan; without one the API returns HTTP 402
`subscription_required` and the scripts stop after the first call. In the app, "Check connection" on the dashboard
makes one live call (at most once a minute) and shows Connected, Not configured, Subscription required or
Connection failed. The result is cached in `backend/.provider_status.json` (git-ignored, no secrets).

Try it without documents: **Try the synthetic demo** on the dashboard, or download the synthetic PDFs/images from
the New audit page and upload them.

## Tests

The backend suite covers extraction (PDF and OCR round trips against ground truth), validation, money calculations,
clause matching, deduction classification, evidence references, PDF generation, provider status and the full
upload → correct → audit → appeal → export workflow, on synthetic documents with hand-computed expected results.

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm run lint
```

## Security notes

- The API key lives only in `.env` (git-ignored) and is held as a `SecretStr`; errors and logs redact it. Health endpoints report whether it is set, never its value.
- Uploaded files are not persisted: they are processed in memory and only extracted text and fields are saved.
- Uploads are limited to 15 MB and PDF, image or text types.
