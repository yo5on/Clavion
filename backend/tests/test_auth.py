"""Authentication tests use fresh temporary SQLite databases and synthetic documents only."""

import hashlib
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth, db
from app.core.config import Settings, settings
from app.demo import fixtures
from app.main import create_app
from app.password import hash_password, verify_password
from .synthetic_cases import CASES

PASSWORD = "synthetic owner password only"
ORIGIN = "https://clavion.test"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def secured(tmp_path, monkeypatch, password_hash):
    engine = create_engine(f"sqlite:///{(tmp_path / 'auth-test.db').as_posix()}",
                           connect_args={"check_same_thread": False})
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", factory)
    monkeypatch.setattr(auth, "SessionLocal", factory)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(password_hash))
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    monkeypatch.setattr(settings, "auth_cookie_samesite", "lax")
    monkeypatch.setattr(settings, "cors_origins", ORIGIN)
    with TestClient(create_app(), base_url="https://api.clavion.test", headers={"Origin": ORIGIN}) as client:
        yield client
    engine.dispose()


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"password": password})


def test_every_registered_endpoint_is_gated_before_validation_or_db_access(secured, monkeypatch):
    def no_database(*args, **kwargs):
        raise AssertionError("unauthenticated request reached the database")

    monkeypatch.setattr(auth, "SessionLocal", no_database)
    monkeypatch.setattr(db, "SessionLocal", no_database)
    checked = set()
    endpoints = {(method.upper(), path) for path, methods in secured.app.openapi()["paths"].items()
                 for method in methods}
    for route in secured.app.routes:
        for method in getattr(route, "methods", ()):
            endpoints.add((method, route.path))
    for method, template in endpoints:
        if (method, template) in auth.PUBLIC or method == "OPTIONS":
            continue
        path = template.replace("{case_id}", "unknown").replace("{doc_type}", "bill")
        response = secured.request(method, path)
        assert response.status_code == 401, (method, path, response.text)
        if method != "HEAD":
            assert response.json() == {"detail": "authentication required"}
        assert response.headers["cache-control"] == "no-store"
        checked.add(template)
    assert {"/api/cases", "/api/cases/{case_id}/documents/{doc_type}",
            "/api/cases/{case_id}/audit", "/api/cases/{case_id}/appeal",
            "/api/cases/{case_id}/export.pdf", "/api/demo/documents/{doc_type}",
            "/api/health", "/docs", "/redoc", "/openapi.json"} <= checked


def test_login_cookie_and_hashed_persistent_session(secured):
    assert secured.get("/api/auth/session").json() == {"enabled": True, "authenticated": False}
    assert login(secured, "incorrect").status_code == 401
    response = login(secured)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "__Host-clavion=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=lax" in cookie and "Path=/" in cookie and "Domain=" not in cookie
    token = secured.cookies.get(auth.cookie_name())
    with db.SessionLocal() as session:
        rows = list(session.scalars(select(db.OwnerSession)))
        assert len(rows) == 1 and rows[0].token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in repr(rows[0].__dict__)
    assert secured.get("/api/health").status_code == 200
    assert secured.get("/api/auth/session").json()["authenticated"] is True
    # New application instance/connection pool, same SQLite file: no in-memory session dependency.
    with TestClient(create_app(), base_url="https://api.clavion.test") as restarted:
        restarted.cookies.set(auth.cookie_name(), token)
        assert restarted.get("/api/cases").status_code == 200


def test_logout_revokes_replayed_cookie_and_is_idempotent(secured):
    assert login(secured).status_code == 200
    token = secured.cookies.get(auth.cookie_name())
    assert secured.post("/api/auth/logout").status_code == 200
    assert secured.get("/api/cases").status_code == 401
    secured.cookies.set(auth.cookie_name(), token)
    assert secured.get("/api/cases").status_code == 401
    assert secured.post("/api/auth/logout").status_code == 200


def test_expiration_and_password_rotation_invalidate_sessions(secured, monkeypatch):
    assert login(secured).status_code == 200
    token = secured.cookies.get(auth.cookie_name())
    with db.SessionLocal() as session:
        row = session.get(db.OwnerSession, auth.token_hash(token))
        expires_at = row.expires_at
        row.expires_at = 0
        session.commit()
    # The browser cookie is still valid: the server must enforce its own expiry.
    assert secured.get("/api/cases").status_code == 401
    assert not secured.get("/api/auth/session").json()["authenticated"]
    with db.SessionLocal() as session:
        session.get(db.OwnerSession, auth.token_hash(token)).expires_at = expires_at
        session.commit()
    assert secured.get("/api/cases").status_code == 200
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(hash_password("different synthetic password")))
    assert secured.get("/api/cases").status_code == 401


def test_relogin_rotates_current_session(secured):
    assert login(secured).status_code == 200
    first = secured.cookies.get(auth.cookie_name())
    assert login(secured).status_code == 200
    assert first != secured.cookies.get(auth.cookie_name())
    secured.cookies.clear()
    secured.cookies.set(auth.cookie_name(), first)
    assert secured.get("/api/cases").status_code == 401


def test_global_login_budget_persists_and_cannot_be_bypassed_with_forwarded_ips(secured, monkeypatch):
    for i in range(auth.LOGIN_LIMIT):
        assert secured.post("/api/auth/login", json={"password": "wrong"},
                            headers={"X-Forwarded-For": f"192.0.2.{i}"}).status_code == 401
    assert login(secured).status_code == 429
    with TestClient(create_app(), base_url="https://api.clavion.test", headers={"Origin": ORIGIN}) as restarted:
        assert login(restarted).status_code == 429
    now = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: now + auth.LOGIN_WINDOW + 1)
    assert login(secured).status_code == 200


def test_concurrent_login_budget_is_atomic(secured):
    with ThreadPoolExecutor(max_workers=8) as workers:
        allowed = list(workers.map(lambda _: auth.reserve_login_attempt(), range(20)))
    assert sum(allowed) == auth.LOGIN_LIMIT


def test_reverse_proxy_root_path_keeps_auth_routes_accessible(secured):
    with TestClient(create_app(), base_url="https://api.clavion.test", root_path="/clavion",
                    headers={"Origin": ORIGIN}) as prefixed:
        assert prefixed.get("/api/auth/session").status_code == 200
        assert login(prefixed).status_code == 200
        assert prefixed.get("/api/cases").status_code == 200


@pytest.mark.parametrize("body", [{}, {"password": None}, {"password": ["x"]}, {"password": "x" * 1025}, []])
def test_invalid_login_never_echoes_inputs(secured, body):
    response = secured.post("/api/auth/login", json=body)
    assert response.status_code == 401 and response.json() == {"detail": "authentication required"}


def test_malformed_and_oversized_login(secured):
    for data in (b"not json", b"\xff", b"a" * 16_385, b"[" * 2000):
        response = secured.post("/api/auth/login", content=data)
        assert response.status_code == 401 and response.json() == {"detail": "authentication required"}


def test_another_browser_cannot_read_or_change_owner_cases_or_documents(secured):
    assert login(secured).status_code == 200
    cid = secured.post("/api/demo/case").json()["id"]
    with TestClient(secured.app, base_url="https://api.clavion.test", headers={"Origin": ORIGIN}) as stranger:
        for token in (None, "forged-session"):
            if token:
                stranger.cookies.set(auth.cookie_name(), token)
            for case_id in (cid, "nonexistent"):
                for method, suffix in (("GET", ""), ("DELETE", ""), ("GET", "/export.pdf"),
                                       ("PUT", "/documents/bill"), ("POST", "/audit"), ("PUT", "/appeal")):
                    response = stranger.request(method, f"/api/cases/{case_id}{suffix}")
                    assert response.status_code == 401 and response.json() == {"detail": "authentication required"}
                response = stranger.post(f"/api/cases/{case_id}/documents/bill",
                                         files={"file": ("bill.txt", b"synthetic")})
                assert response.status_code == 401
    assert secured.get(f"/api/cases/{cid}").status_code == 200


def test_authenticated_upload_audit_correction_appeal_and_download_regression(secured):
    assert login(secured).status_code == 200
    cid = secured.post("/api/cases", json={"title": "Synthetic authenticated audit"}).json()["id"]
    for doc_type, text in fixtures.TEXTS.items():
        response = secured.post(f"/api/cases/{cid}/documents/{doc_type}",
                                files={"file": (f"{doc_type}.txt", text.encode())})
        assert response.status_code == 200
    report = secured.post(f"/api/cases/{cid}/audit").json()["audit"]
    assert report["contestable_total"] == "4447.80" and report["unverified_total"] == "2500.00"
    case = secured.get(f"/api/cases/{cid}").json()
    policy = case["documents"]["policy"]["data"]
    policy["non_payable_items"].append("Registration charges")
    assert secured.put(f"/api/cases/{cid}/documents/policy", json=policy).status_code == 200
    report = secured.post(f"/api/cases/{cid}/audit").json()["audit"]
    assert report["contestable_total"] == "3447.80"
    assert secured.put(f"/api/cases/{cid}/appeal", json={"text": "Synthetic edited appeal"}).status_code == 200
    for kind in ("report", "appeal"):
        response = secured.get(f"/api/cases/{cid}/export.pdf?kind={kind}")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        assert response.headers["cache-control"] == "no-store"
        if kind == "appeal":
            assert "Synthetic edited appeal" in "".join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)
    assert secured.get("/api/demo/documents/bill?format=pdf").content.startswith(b"%PDF")
    assert secured.delete(f"/api/cases/{cid}").status_code == 204


@pytest.mark.parametrize("name", CASES)
def test_authenticated_audits_preserve_hand_calculated_policy_results(secured, name):
    assert login(secured).status_code == 200
    case = CASES[name]
    cid = secured.post("/api/cases", json={"title": case["title"]}).json()["id"]
    for doc_type in ("bill", "policy", "settlement"):
        if case[doc_type] is not None:
            assert secured.post(f"/api/cases/{cid}/documents/{doc_type}",
                                files={"file": (f"{doc_type}.txt", case[doc_type].encode())}).status_code == 200
    response = secured.post(f"/api/cases/{cid}/audit")
    assert response.status_code == 200
    audit = response.json()["audit"]
    expected = case["expected"]
    for key in ("contestable_total", "unverified_total", "supported_total"):
        assert Decimal(audit[key]) == expected[key]
    assert Decimal(audit["total_deductions"]) == expected["total"]
    assert [f["status"] for f in audit["findings"]] == expected["statuses"]


@pytest.mark.parametrize("origin", ["https://evil.test", "null", "https://clavion.test.evil.test", ""])
def test_origin_checks_block_login_logout_and_authenticated_mutations(secured, origin):
    headers = {"Origin": origin}
    assert secured.post("/api/auth/login", json={"password": PASSWORD}, headers=headers).status_code == 403
    assert login(secured).status_code == 200
    assert secured.post("/api/cases", json={"title": "blocked"}, headers=headers).status_code == 403
    assert secured.post("/api/auth/logout", headers=headers).status_code == 403
    assert secured.get("/api/cases").json() == []


def test_missing_origin_is_rejected(secured):
    secured.headers.pop("Origin")
    assert login(secured).status_code == 403


def test_cors_allows_only_explicit_origin_with_credentials_even_on_auth_failure(secured):
    allowed = secured.options("/api/cases", headers={"Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "Content-Type"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    unauthorized = secured.get("/api/cases")
    assert unauthorized.status_code == 401 and unauthorized.headers["access-control-allow-origin"] == ORIGIN
    denied = secured.options("/api/cases", headers={"Origin": "https://evil.test",
                                                   "Access-Control-Request-Method": "POST"})
    assert denied.status_code == 400 and "access-control-allow-origin" not in denied.headers
    assert "access-control-allow-origin" not in secured.get("/api/cases", headers={"Origin": "https://evil.test"}).headers


def test_no_static_database_or_document_routes(secured):
    assert login(secured).status_code == 200
    for path in ("/clavion.db", "/backend/clavion.db", "/uploads/bill.pdf", "/.env", "/data/clavion.db"):
        assert secured.get(path).status_code == 404


def test_password_hash_salt_and_verification(password_hash):
    assert PASSWORD not in password_hash
    assert verify_password(PASSWORD, password_hash)
    assert not verify_password("incorrect", password_hash)
    assert not verify_password("\ud800", password_hash)
    assert hash_password(PASSWORD) != password_hash
    with pytest.raises(ValueError):
        hash_password("short")


@pytest.mark.parametrize("overrides", [
    {"cors_origins": "*"}, {"cors_origins": "https://*.example.com"},
    {"cors_origins": "https://clavion.test/path"}, {"cors_origins": ""},
    {"auth_password_hash": "invalid"}, {"auth_cookie_secure": False},
    {"auth_cookie_secure": False, "auth_cookie_samesite": "none"},
    {"cors_origins": "http://public.example"}, {"auth_session_seconds": 0},
])
def test_invalid_hosted_config_fails_closed(password_hash, overrides):
    values = {"auth_enabled": True, "auth_password_hash": password_hash, "cors_origins": ORIGIN}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(values | overrides))


def test_auth_can_be_disabled_for_existing_local_workflow():
    with TestClient(create_app()) as local:
        assert local.get("/api/health").status_code == 200
        assert local.get("/api/auth/session").json() == {"enabled": False, "authenticated": True}
        assert login(local).status_code == 403


def test_existing_database_upgrade_preserves_cases_and_sessions_across_restart(tmp_path, monkeypatch, password_hash):
    path = tmp_path / "legacy.db"
    report = json.dumps({"demo": False, "documents": {}, "audit": None, "appeal": None})
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE cases (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200) NOT NULL, "
                           "status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, report JSON)")
        connection.execute("INSERT INTO cases VALUES (?, ?, ?, ?, ?)",
                           ("legacy", "SYNTHETIC legacy claim", "draft", "2026-01-01 00:00:00", report))
        before = connection.execute("SELECT * FROM cases").fetchall()
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", factory)
    monkeypatch.setattr(auth, "SessionLocal", factory)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(password_hash))
    monkeypatch.setattr(settings, "cors_origins", ORIGIN)
    try:
        with TestClient(create_app(), base_url="https://api.clavion.test", headers={"Origin": ORIGIN}) as client:
            assert client.get("/api/cases/legacy").status_code == 401
            assert login(client).status_code == 200
            assert client.get("/api/cases/legacy").json()["title"] == "SYNTHETIC legacy claim"
            token = client.cookies.get(auth.cookie_name())
        engine.dispose()  # Force fresh connections on restart.
        with TestClient(create_app(), base_url="https://api.clavion.test", headers={"Origin": ORIGIN}) as restarted:
            restarted.cookies.set(auth.cookie_name(), token)
            assert restarted.get("/api/cases/legacy").status_code == 200
            assert restarted.post("/api/auth/logout").status_code == 200
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT * FROM cases").fetchall() == before
            assert connection.execute("SELECT COUNT(*) FROM owner_sessions").fetchone()[0] == 0
            assert connection.execute("SELECT attempts FROM login_throttle WHERE id=1").fetchone()[0] == 1
    finally:
        engine.dispose()


def test_enabled_local_authentication_uses_separate_loopback_cookie(secured, monkeypatch, password_hash):
    Settings(_env_file=None, auth_enabled=True, auth_password_hash=password_hash,
             auth_cookie_secure=False, cors_origins="http://localhost:5173")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "cors_origins", "http://localhost:5173")
    with TestClient(create_app(), base_url="http://localhost:8000",
                    headers={"Origin": "http://localhost:5173"}) as local:
        assert local.get("/api/cases").status_code == 401
        response = login(local)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "clavion-local=" in cookie and "HttpOnly" in cookie and "Secure" not in cookie
        assert local.get("/api/cases").status_code == 200
        assert local.post("/api/auth/logout").status_code == 200
        assert local.get("/api/cases").status_code == 401
