# Running the complete application online

GitHub Pages serves the React frontend only. FastAPI, offline OCR and SQLite need
a Python host with persistent storage. The current Pages workflow configures no
backend origin; publishing that frontend does not make audits work.

## Recommendation

Keep local execution as the default. For personal online use, start with one
backend instance and SQLite on a persistent volume, behind a private network or
an authenticated reverse proxy. Prefer a single origin serving the built frontend
and proxying `/api` to FastAPI: this also protects downloads without cross-origin
login complications. A small existing Linux server is the cheapest option if one
is already available; its operator must maintain HTTPS, security updates and backups.

No authentication or per-user isolation exists in the application. Anyone who can
reach the API can list, read, modify and delete all cases. CORS is not authentication.
Do not expose it publicly with real records. Protect every API route, including
PDF exports and API documentation; a public multi-user service needs authentication
and case ownership checks before release.

## Hosting comparison

Provider documentation checked 2026-11-08. USD prices exclude tax and can change;
these are starting costs, not a measured CLAVION capacity estimate.

| Option | Backend and database | Cost and tradeoff |
| --- | --- | --- |
| Existing private Linux host | Uvicorn + SQLite on local persistent disk | No new hosting bill if already owned; maintain the OS, HTTPS and backups yourself. Best fit for local-first personal use. |
| Railway | Python service + mounted volume for SQLite | [Hobby has a $5 monthly minimum including $5 usage](https://railway.com/pricing); extra usage costs more. [Volumes](https://docs.railway.com/volumes/reference) preserve the database. Simple managed starting point; measure OCR memory and set spending limits. |
| Fly.io | Machine + volume for SQLite | [Usage pricing](https://fly.io/docs/about/pricing/): 1 GB Machine starts at $6.70 per 30 days in the listed lowest-cost regions, plus $0.15/GB-month volume and transfer. More machine/volume operations to manage; OCR sizing remains unmeasured. |
| Render | Paid Python web service + persistent disk | [Free services](https://render.com/docs/free) have ephemeral storage and no persistent disks, unsuitable for saved cases. [Persistent disks](https://render.com/docs/disks) require a paid service; consult [current pricing](https://render.com/pricing) for compute plus storage. |

Use one replica and one Uvicorn worker initially. SQLite should stay on the attached
local filesystem, not independent disks on multiple replicas. PostgreSQL is a
future option for shared/multi-instance use, not a drop-in switch here: `db.py`
currently uses SQLite-specific connection arguments and a SQLite PRAGMA.
No paid or external AI API is needed on any host; the same local parsers, OCR and
deterministic Decimal calculations run on the selected server.

## Backend configuration (preparation only)

From the `backend` directory, install `requirements.txt` using a supported Python
runtime with compatible ONNX wheels, then start:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
```

Set `PORT` through the host (for example `8000`). Bind to loopback instead when a
reverse proxy on the same machine handles access. Create/mount `/data` first and set:

```dotenv
DATABASE_URL=sqlite:////data/clavion.db
CORS_ORIGINS=https://your-frontend.example
LOG_LEVEL=INFO
```

For Pages, the allowed origin is `https://yo5on.github.io`, without `/Clavion/`.
Keep the database outside the release directory. Use a fresh empty database for
synthetic verification; do not copy the local `.env`, `clavion.db` or user records.
Use SQLite's backup API for consistent backups and test restoration to a separate
file. Never commit a database, backup or credentials.

## Frontend configuration

Without configuration, requests use same-origin `/api`. `CLAVION_API_URL` in
`vite.config.ts` affects the development proxy only, not production builds.
For a separately hosted backend, set this public build-time value before building:

```dotenv
VITE_API_ORIGIN=https://your-backend.example
```

The value is the backend origin (no `/api` suffix), optionally with a reverse-proxy
path prefix. The client applies it to JSON requests, uploads, PDF exports and demo
downloads. Use HTTPS with an HTTPS frontend. Never place passwords, tokens or other
secrets in a `VITE_` variable: these values become public JavaScript.

The Pages workflow deliberately remains unchanged. Configuring an origin and
rebuilding/publishing it is a separate deployment requiring approval. `VITE_BASE`
still controls the frontend asset/router path; it does not select a backend.
Cross-origin cookie-based access gateways need additional credential/CORS handling
that this client does not implement; prefer the single-origin protected setup above.

Hosting moves processing and extracted records onto the server. It is no longer
processing exclusively on the user's machine, even though it still calls no AI
services. Choose location, access and retention appropriate to the documents.

## Verification before any approved deployment

Use synthetic documents only: check `/api/health`, create a case, upload all three
documents, review, audit, edit the appeal, download PDFs, then delete the case.
Restart/redeploy the backend and confirm a retained synthetic case survives.
Verify unauthenticated access is blocked for the API and downloads, check a backup
restore, and measure scanned-PDF OCR memory and latency before choosing capacity.
These host-level checks have not been performed by the local routing change.
