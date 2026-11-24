<div align="center">
<samp><b>CLAVION — Insurance Claims Intelligence</b></samp>
</div>

---

> Every deduction deserves an explanation.

<samp>Clavion audits Indian health insurance claim settlements. You upload the hospital bill, the policy wording and the</samp>
<samp>insurer's settlement letter. Clavion reads them locally, recalculates every deduction with exact decimal arithmetic,</samp>
<samp>shows the clause and bill lines each conclusion rests on, and drafts an appeal you can edit statement by statement.</samp>

<samp>**Local-first, no AI APIs.** Text extraction (pypdf, RapidOCR on ONNX), parsing, rules and PDF generation all run on</samp>
<samp>your machine. No document, field or result is sent to any external service. There is no model inference anywhere</samp>
<samp>in the pipeline: every conclusion comes from a named rule you can read in `backend/app/services/rules.py`.</samp>

<samp>Clavion never says a deduction is illegal, unlawful or guaranteed to be recoverable. A finding is either</samp>
<samp>**supported** by the documents, **potentially contestable** (the documents do not support part of it), or</samp>
<samp>**needs clarification** (the documents cannot decide, and Clavion says what is missing).</samp>

<samp>See [`docs/PRODUCT_AUDIT.md`](docs/PRODUCT_AUDIT.md) for the critical product review behind this version, its</samp>
<samp>priorities and its known limitations.</samp>


---

<div align="center"><samp><b>How an audit works</b></samp></div>

1. <samp>**Upload** (PDF, PNG/JPG/TIFF/WEBP/BMP, or UTF-8 text). The file signature must match the extension; size,</samp>
<samp>   page count and image pixel count are bounded; encrypted and malformed PDFs are rejected with a clear message.</samp>
<samp>   PDFs use their text layer, and pages with too little text are OCR'd. Low OCR confidence is reported. Uploading</samp>
<samp>   the same file into two slots is refused, and a file that reads like the wrong document type is flagged.</samp>
2. <samp>**Extract** with deterministic parsers. Every field carries a status — *extracted*, *inferred*, *missing* or</samp>
<samp>   *corrected* — and, where it came from the document, its page, line and the original text.</samp>
3. <samp>**Review**. Each field shows where it was read ("Read from p. 2, line 14"). Corrections are validated and</samp>
<samp>   marked *corrected*, keeping the original source for comparison.</samp>
4. <samp>**Audit** (`services/rules.py`, `services/audit.py`). Each deduction is classified and run through one rule.</samp>
<samp>   Every finding answers eight questions: what happened, the amount, what the insurer stated, the policy clause,</samp>
<samp>   the evidence, why it may be contestable, what is missing, and the next step. It also lists the rule's</samp>
<samp>   conditions (met / not met / could not be checked). Consistency checks then cross-check the three documents.</samp>
5. <samp>**Appeal**. The letter is built from typed statements: *from your documents* (source facts with page/line</samp>
<samp>   references), *Clavion calculation*, *suggested wording* and *letter formality*. Each can be edited or left out.</samp>
<samp>   Report and letter export to PDF (`Cache-Control: no-store`).</samp>

<div align="center"><samp><b>Rules (version 2026.11-1)</b></samp></div>

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

<samp>Differences up to Rs 1.00 are treated as rounding. A room-category limit ("single private room") cannot be turned</samp>
<samp>into rupees, so such deductions stay *needs clarification* and Clavion asks for the eligible room rent.</samp>

<div align="center"><samp><b>Consistency checks</b></samp></div>

<samp>Settlement arithmetic (C-REC-01/02), bill arithmetic (C-REC-03/04), claim vs bill total (C-REC-05), paid vs approved</samp>
<samp>(C-REC-06), duplicate bill lines and deductions (C-DUP-01/02), deductions exceeding what was billed (C-OVL-01), room</samp>
<samp>days vs length of stay (C-STAY-01), cited clauses present in the policy (C-CIT-01), policy number / patient /</samp>
<samp>hospital consistency (C-ID-01..03), approved within sum insured (C-SI-01), unreviewed extraction warnings</samp>
<samp>(C-DOC-01). A check whose inputs are missing is reported as *not checked*, never as passed.</samp>


---

<div align="center"><samp><b>Architecture</b></samp></div>

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


---

<div align="center"><samp><b>Setup</b></samp></div>

<samp>Requirements: Python 3.11+, Node 20+. Run the backend and the frontend in two terminals.</samp>

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                 # open http://localhost:5173
```

<samp>No configuration is needed: authentication is off by default, the API binds to `127.0.0.1`, and the SQLite</samp>
<samp>database is created at `backend/clavion.db` on first start. `.env.example` lists the optional settings.</samp>
<samp>The first OCR of an image can take a few seconds while the local ONNX model loads.</samp>

<samp>Try it without your own documents: **Open the demo claim** on the dashboard, or download the synthetic PDFs/images</samp>
<samp>from the New audit page and upload them. Everything derived from synthetic documents is labelled DEMO.</samp>


---

<div align="center"><samp><b>Online use</b></samp></div>

<samp>The frontend is published at **https://yo5on.github.io/Clavion/** for reference only. GitHub Pages hosts static</samp>
<samp>files: it cannot run FastAPI, OCR or SQLite, so that page shows a "no Clavion backend available" message and</samp>
<samp>cannot audit anything. Full auditing requires the backend running locally as described above.</samp>
<samp>See [hosting options and configuration](docs/HOSTING.md) for the next steps.</samp>
<samp>Single-owner authentication is available; follow [secure configuration and recovery](docs/SECURITY.md)</samp>
<samp>before exposing the API. Authentication is disabled by default for local use.</samp>


---

<div align="center"><samp><b>Known limitations</b></samp></div>

- <samp>No hosted backend: the public page is the interface only; audits run locally.</samp>
- <samp>Parsers are deterministic and tuned to common Indian hospital-bill, policy and settlement-letter layouts.</samp>
<samp>  Unusual layouts or poor scans need manual correction on the review screen (every field is editable).</samp>
- <samp>OCR quality depends on the scan; low-confidence pages are flagged, not silently trusted.</samp>
- <samp>Single owner only: no multi-user accounts, sharing or registration.</samp>
- <samp>Findings explain what the documents do and do not support; they are not legal advice or a guarantee of recovery.</samp>


---

<div align="center"><samp><b>Tests</b></samp></div>

```bash
cd backend && python -m pytest -q
cd frontend && npm test && npm run lint && npm run build
```

<samp>261 backend tests and 11 frontend tests. Highlights:</samp>

- <samp>`tests/synthetic_cases.py` — nine synthetic claims (simple, room rent + proportionate, co-pay, sub-limit and</samp>
<samp>  non-payable, missing clauses, poor OCR scan, exclusions, two-page bill with "/-" amounts and rounding, conflicting</samp>
<samp>  documents with a table-format letter). Each is rendered to PDF (or a degraded scan), read back, parsed and</samp>
<samp>  audited; every amount is compared with a hand calculation written in the comments.</samp>
- <samp>`tests/test_rules.py` — each rule and check in isolation, including mixed room rates, the rounding boundary,</samp>
<samp>  co-pay on the gross claim, subset reproduction of a proportionate figure, and readiness states.</samp>
- <samp>`tests/test_document_intelligence.py` — page/line provenance across pages, field statuses, table-format</samp>
<samp>  letters, deduction lines without amounts, dates, room-category policies.</samp>
- <samp>`tests/test_security.py` — signature mismatch, malformed and encrypted PDFs, decompression bomb, size limit,</samp>
<samp>  duplicate upload, client path stripping, case isolation and deletion, audit trail without document text,</samp>
<samp>  appeal statement editing and export.</samp>


---

<div align="center"><samp><b>Privacy and security</b></samp></div>

- <samp>No external calls. No API keys. Uploaded files are processed in memory and never written to disk; only the</samp>
<samp>  extracted text and fields are stored, in the local SQLite database (`secure_delete` on).</samp>
- <samp>Deleting a case removes its text, fields, audit and appeal.</samp>
- <samp>The audit trail records events (uploads, corrections, audits, appeal saves) but never document text or amounts.</samp>
- <samp>Uploads: 15 MB, 60 PDF pages, 40 megapixels per image; signature checked; client paths stripped from file names.</samp>
- <samp>Optional single-owner password authentication protects the API and downloads with expiring, revocable</samp>
<samp>  sessions. With authentication disabled, bind only to loopback. There is no public registration or multi-user mode.</samp>
