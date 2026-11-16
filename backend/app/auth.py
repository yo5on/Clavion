"""Single-owner access gate. Cookie secrets are random; only their hashes reach SQLite."""

import hashlib
import json
import secrets
import time

from fastapi import APIRouter, Request
from sqlalchemy import delete, or_, case
from sqlalchemy.dialects.sqlite import insert
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .core.config import settings
from .db import LoginThrottle, OwnerSession, SessionLocal
from .password import verify_password

router = APIRouter(prefix="/api/auth")
LOGIN_WINDOW = 900
LOGIN_LIMIT = 5
PUBLIC = {("GET", "/api/auth/session"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout")}


def cookie_name() -> str:
    return "__Host-clavion" if settings.auth_cookie_secure else "clavion-local"


def credential_key() -> str:
    return hashlib.sha256(settings.auth_password_hash.get_secret_value().encode()).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticated(request: Request) -> bool:
    token = request.cookies.get(cookie_name(), "")
    if not token or len(token) > 128:
        return False
    with SessionLocal() as db:
        session = db.get(OwnerSession, token_hash(token))
        return bool(session and session.expires_at > int(time.time())
                    and secrets.compare_digest(session.credential_key, credential_key()))


def error(status: int) -> JSONResponse:
    messages = {401: "authentication required", 403: "request not permitted", 429: "too many login attempts; try later"}
    return JSONResponse({"detail": messages[status]}, status_code=status,
                        headers={"Retry-After": str(LOGIN_WINDOW)} if status == 429 else {})


class OwnerAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = None
        if settings.auth_enabled and request.method != "OPTIONS":
            path = request.scope["path"]
            root = request.scope.get("root_path", "")
            if root and path.startswith(root + "/"):
                path = path[len(root):]
            if (request.method, path) not in PUBLIC:
                if not await run_in_threadpool(authenticated, request):
                    response = error(401)
            if response is None and request.method not in ("GET", "HEAD"):
                if request.headers.get("origin") not in settings.allowed_origins:
                    response = error(403)
        if response is None:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def reserve_login_attempt() -> bool:
    now = int(time.time())
    # One global, persistent budget prevents IP/header spoofing from bypassing the owner login limit.
    expired = LoginThrottle.window_start <= now - LOGIN_WINDOW
    statement = insert(LoginThrottle).values(id=1, window_start=now, attempts=1).on_conflict_do_update(
        index_elements=[LoginThrottle.id],
        set_={"window_start": case((expired, now), else_=LoginThrottle.window_start),
              "attempts": case((expired, 1), else_=LoginThrottle.attempts + 1)},
        where=or_(expired, LoginThrottle.attempts < LOGIN_LIMIT))
    with SessionLocal() as db:
        allowed = db.execute(statement).rowcount == 1
        db.commit()
        return allowed


@router.get("/session")
def session_status(request: Request):
    return {"enabled": settings.auth_enabled,
            "authenticated": not settings.auth_enabled or authenticated(request)}


@router.post("/login")
async def login(request: Request):
    if not settings.auth_enabled:
        return error(403)
    if not await run_in_threadpool(reserve_login_attempt):
        return error(429)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 16_384:
            return error(401)
        raw.extend(chunk)
    try:
        body = json.loads(raw)
        password = body.get("password") if isinstance(body, dict) else None
    except (ValueError, UnicodeError, RecursionError):
        password = None
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        return error(401)
    if not await run_in_threadpool(verify_password, password, settings.auth_password_hash.get_secret_value()):
        return error(401)
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with SessionLocal() as db:
        db.execute(delete(OwnerSession).where(or_(OwnerSession.expires_at <= now,
                                                OwnerSession.credential_key != credential_key())))
        # Reauthentication replaces this browser's old session instead of leaving a usable duplicate.
        old = request.cookies.get(cookie_name(), "")
        if old:
            db.execute(delete(OwnerSession).where(OwnerSession.token_hash == token_hash(old)))
        db.add(OwnerSession(token_hash=token_hash(token), credential_key=credential_key(),
                            expires_at=now + settings.auth_session_seconds))
        db.commit()
    response = JSONResponse({"authenticated": True})
    response.set_cookie(cookie_name(), token, max_age=settings.auth_session_seconds, path="/",
                        secure=settings.auth_cookie_secure, httponly=True, samesite=settings.auth_cookie_samesite)
    return response


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(cookie_name(), "")
    if token:
        with SessionLocal() as db:
            db.execute(delete(OwnerSession).where(OwnerSession.token_hash == token_hash(token)))
            db.commit()
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(cookie_name(), path="/", secure=settings.auth_cookie_secure,
                           httponly=True, samesite=settings.auth_cookie_samesite)
    return response
