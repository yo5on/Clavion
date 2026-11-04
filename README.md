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
| 2. Document intelligence | Upload, parsing, structured extraction | Not started |
| 3. Claim auditing | Clause retrieval, deduction analysis, calculations, verification | Not started |
| 4. Product experience | Dashboard data, findings, appeal + PDF, case history | Not started |
| 5. Reliability | Synthetic eval set, integration tests, security review | Not started |

## Architecture

```
frontend/  React 19 + TypeScript + Vite + Tailwind v4 + lucide-react
  src/api.ts            typed API client (mirrors backend Pydantic models)
  src/components/       Layout (sidebar shell), Logo
  src/pages/            Dashboard, placeholders for upcoming pages
backend/   Python + FastAPI + Pydantic + SQLAlchemy (SQLite)
  app/core/config.py    settings from env / .env (key held as SecretStr)
  app/services/bharatcode_client.py   BharatCode client: auth, timeouts, retries, error classification
  app/services/calculations.py        deterministic money maths
  app/schemas/bill.py   bill extraction schema + Python arithmetic checks
  app/db.py             engine, Case model (stores results, not uploaded documents)
  app/main.py           app, CORS, /api/health, /api/health/llm
  scripts/test_*.py     live capability tests (auth, inference, JSON, image, tools) on a SYNTHETIC bill
  tests/                pytest
```

The Vite dev server proxies `/api` to `localhost:8000`, so the browser never sees the API key.

Planned audit pipeline: ingestion → extraction → bill normalisation → clause retrieval → deduction analysis →
deterministic calculation → independent verification → report. The model does extraction and reasoning; Python does
all money arithmetic.

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
`subscription_required` and the scripts stop after the first call.

## Tests

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm run lint
```

## Security notes

- The API key lives only in `.env` (git-ignored) and is held as a `SecretStr`; errors and logs redact it. Health endpoints report whether it is set, never its value.
- Uploaded documents are not persisted (from Phase 2 on, they are processed in memory and only extracted results are saved).
