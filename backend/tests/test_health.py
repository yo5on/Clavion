from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import app
from app.services import bharatcode_client as bc


def test_health_reports_db_and_config():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] is True
    assert body["model"] == settings.bharatcode_model


def test_llm_health_handles_unreachable_catalog(monkeypatch):
    def boom(self):
        raise bc.BharatCodeError("connection", "network down")

    monkeypatch.setattr(bc.BharatCodeClient, "list_models", boom)
    with TestClient(app) as c:
        body = c.get("/api/health/llm").json()
    assert body["reachable"] is False and body["error"] == "catalog: connection"


def test_llm_health_reports_missing_key(monkeypatch):
    monkeypatch.setattr(bc.BharatCodeClient, "list_models",
                        lambda self: [{"id": settings.bharatcode_model, "metadata": {"toolCalling": True}}])
    monkeypatch.setattr(settings, "bharatcode_api_key", SecretStr(""))
    with TestClient(app) as c:
        body = c.get("/api/health/llm?live=true").json()
    assert body["model_listed"] is True and body["model_capabilities"] == {"toolCalling": True}
    assert body["live_inference"] is False and body["error"] == "inference: not_configured"


def test_api_key_never_leaves_the_server(monkeypatch):
    secret = "sk-test-SECRET-123"
    monkeypatch.setattr(settings, "bharatcode_api_key", SecretStr(secret))
    monkeypatch.setattr(bc.BharatCodeClient, "list_models", lambda self: [])
    with TestClient(app) as c:
        texts = [c.get(p).text for p in ("/api/health", "/api/health/llm", "/openapi.json")]
    assert all(secret not in t for t in texts)
    assert secret not in repr(settings) and secret not in str(settings.model_dump())
