# Single-owner security

## Scope and threat model

This deployment has exactly one owner. There is no username directory, public
registration, password-reset email, invitation flow or second user. All cases in
the configured database belong to that owner. An unauthenticated browser or
forged session must not discover, upload, change, audit, export or delete records.
The access gate also covers unknown URLs and validation failures, returning the
same `401 {"detail":"authentication required"}` before routing/body parsing.
This prevents case/document existence probes from producing different errors.

The design addresses remote unauthorized access, credential guessing, session
fixation/replay after logout, cross-site request forgery and accidental caching.
It does not protect against a compromised host/browser, XSS on a trusted frontend,
stolen active cookies, denial of service, or a malicious authenticated owner.
This is not a multi-user application or a medical-data compliance certification.

## Authentication design

- Passwords use a random 128-bit salt and PBKDF2-HMAC-SHA256 with 600,000 iterations,
  verified with constant-time digest comparison. This uses Python's standard library;
  no new dependency or external API is needed. See the
  [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- A successful login creates a random 256-bit token. Only its SHA-256 hash, credential
  fingerprint and absolute expiry are stored in SQLite's `owner_sessions` table.
  The token never appears in a JSON response, URL, localStorage or sessionStorage.
  Default lifetime is eight hours; it does not slide on activity.
- The production cookie is `__Host-clavion`, `Secure`, `HttpOnly`, `Path=/`, with no
  Domain. SameSite defaults to Lax. Logging in again replaces this browser's old
  session; logout deletes the server record, so replay fails. Changing the password
  hash invalidates all existing sessions, including across process restarts.
- A global atomic SQLite login budget admits five attempts per 15-minute window,
  including successful, malformed and incorrect requests. It persists across
  restarts and ignores spoofable forwarded-IP headers. This is deliberately
  conservative for one owner. Attackers can exhaust that budget and temporarily
  prevent owner login; use edge rate limiting/private ingress for denial-of-service
  protection. Keep server time synchronized.
- State-changing requests, including login/logout, require an exact Origin in
  `CORS_ORIGINS`; missing, `null` and unlisted Origins are rejected. CORS allows
  credentials only for explicit origins, never `*`. These checks follow the
  [OWASP origin-validation guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
  Non-browser clients must send an allowed Origin and maintain the session cookie;
  the Origin header alone never authenticates a caller.
- Responses passing through the gate use `Cache-Control: no-store`, `nosniff`
  and `Referrer-Policy: no-referrer`. Do not override these in a CDN or reverse proxy.

## Protected surface

When `AUTH_ENABLED=true`, the middleware protects all routes by default, including
new routes added later. It runs before multipart uploads or request validation:

| Method | Endpoint | Data/operation |
| --- | --- | --- |
| GET | `/api/providers` | Local processing capabilities |
| GET / POST | `/api/cases` | List / create database records |
| GET / DELETE | `/api/cases/{case_id}` | Extracted text, fields, provenance, history, audit and appeal / deletion |
| POST / PUT | `/api/cases/{case_id}/documents/{doc_type}` | Upload/extract / correct stored document fields |
| POST | `/api/cases/{case_id}/audit` | Run deterministic rules and save results/appeal |
| PUT | `/api/cases/{case_id}/appeal` | Edit stored appeal |
| GET | `/api/cases/{case_id}/export.pdf` | Report / appeal download |
| POST | `/api/demo/case` | Create/audit synthetic records |
| GET | `/api/demo/documents/{doc_type}` | Synthetic PDF / PNG download |
| GET | `/api/health` | Database/OCR/version details |
| GET / HEAD | `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json` | API documentation/schema |

Only `GET /api/auth/session` (enabled/authenticated booleans),
`POST /api/auth/login`, `POST /api/auth/logout`, and CORS OPTIONS requests are public.
Logout is idempotent and only revokes the supplied cookie. Login and logout still
require an allowed Origin. The status route reveals no owner or case information.
There is no raw uploaded-file download route or static backend directory mount.
Original uploads are processed and discarded; extracted text lives in SQLite.
Database schema initialization happens at startup, outside request authentication.
Session checks and login throttling use only the authentication tables; case
database operations run only after the access gate succeeds.

## Configuration and secret generation

Local use is unchanged: `AUTH_ENABLED=false` by default, Vite proxies `/api`, and
Uvicorn's default loopback bind remains appropriate. Never use this setting on a
public interface. The server logs a warning when authentication is disabled.

Generate a long unique password in a password manager. From `backend`, run:

```sh
python -m app.password
```

The helper prompts twice without echoing the password and prints only the salted
hash. It works without loading settings or opening the database, including during
recovery from invalid configuration. Keep the output private too: it permits
offline password guessing. Set it as `AUTH_PASSWORD_HASH` using the host's secret
environment UI or a protected environment file outside the served directory.
Copy the entire hash literally, including `$` characters; do not let a shell or
deployment template expand them. Never pass the plaintext password on a command
line, commit it, or put it in a `VITE_` variable. There is no signing key to generate:
session secrets are generated by the OS-backed `secrets` module at each login.

```dotenv
AUTH_ENABLED=true
# AUTH_PASSWORD_HASH is set separately in the host's secret environment.
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTH_SESSION_SECONDS=28800
CORS_ORIGINS=https://clavion.example.com
DATABASE_URL=sqlite:////data/clavion.db
```

Configuration fails at startup if enabled authentication lacks a correctly formed
hash, the expiry is outside 300–86400 seconds, or origins contain wildcards, paths,
credentials or invalid schemes. Production frontend origins must use HTTPS.
For local authentication tests only, explicitly set `AUTH_COOKIE_SECURE=false`
and use loopback frontend origins such as `http://localhost:5173`; this uses the
separate `clavion-local` cookie. Never use insecure cookies for hosted access.

Prefer HTTPS frontend and API on one origin, with `/api` proxied to Uvicorn on a
private/loopback interface. Same-site HTTPS subdomains also work: set the exact
frontend origin and `VITE_API_ORIGIN` when building. The frontend uses credentialed
fetches, including PDF exports; demo download links use the browser cookie.
For unrelated frontend/backend sites, `AUTH_COOKIE_SAMESITE=none` requires Secure;
third-party cookie blocking can still prevent sessions. Prefer a same-site domain
over weakening browser settings. Pages remains a static frontend only.

Terminate HTTPS at a trusted proxy, redirect HTTP to HTTPS, configure HSTS there,
and prevent direct access to the internal Uvicorn port. Trust forwarded headers
only from that proxy, restrict Host names there, and enforce upload size/time and
connection limits before the application. Mount persistent storage outside static
roots. Serve **only `frontend/dist`** as frontend assets; never serve the repository,
`backend`, `.env`, database files, backups or upload directories. Use one replica
and one worker initially. SQLite on local persistent storage is required.

The frontend shows a password form when required and unmounts case views on 401
or successful sign-out. Session expiry is enforced by the server on each request;
a page already open may retain rendered information until its next request.
Use a trusted device and sign out when finished. Downloads already saved to a
device cannot be revoked by logout.

## Backup and recovery

Use a restricted persistent directory, encryption at rest and encrypted backups;
SQLite itself is not encrypted. Run consistent backups through SQLite's backup API
(for example, an administrator's `sqlite3` `.backup` command), not a raw file copy
while writes are active. Restrict file permissions to the service account and a
designated backup operator. Backups contain medical text, case data, session hashes
and throttle state; retain them only as long as needed and never place them in Git
or a public bucket. Protect the password hash separately in your secret manager.

To recover a forgotten/compromised password, keep ingress private, generate a fresh
hash with the helper, replace `AUTH_PASSWORD_HASH` and restart the service. The new
credential fingerprint revokes old sessions without touching cases. There is no
public password reset. For immediate administrative revocation without changing
the password, stop the service and run `DELETE FROM owner_sessions;` against the
configured database using a trusted SQLite admin tool, then restart. Do not delete
the database or the `cases` table. A denied login budget expires in 15 minutes;
after securing ingress, an administrator can clear only `login_throttle` for recovery.

Test restore into a separate private database/path. After restoring, rotate the
password hash and clear restored `owner_sessions` before reopening ingress so old
cookies cannot become usable again. Recheck synthetic upload, audit, appeal,
export, logout and case survival across restart. Never test recovery on the user's
local database. Authentication tables are added by `create_all`; existing case
records and Decimal/policy schemas are unchanged.

## Remaining boundaries

There is no MFA, multi-user isolation, remote session-management screen or edge
DoS service. Any holder of a current owner session can access every case. Origin
validation assumes the configured frontend is trusted; it cannot prevent XSS there.
Authentication defaults to disabled for compatibility, so hosted configuration
must explicitly enable it. HTTPS/proxy policy, browser cookie behavior, filesystem
permissions, host security, capacity and backup restoration require deployment
verification; local tests cannot certify those properties. No host is deployed by
this change and no real records are used in tests.
