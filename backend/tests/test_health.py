from fastapi.testclient import TestClient

from app import llm
from app.config import settings
from app.main import app


def test_health_reports_db_and_config():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] is True
    assert body["model"] == settings.bharatcode_model
    assert "api_key" not in r.text.lower()


def test_llm_health_handles_unreachable_catalog(monkeypatch):
    def boom():
        raise ConnectionError("network down")

    monkeypatch.setattr(llm, "list_models", boom)
    with TestClient(app) as c:
        body = c.get("/api/health/llm").json()
    assert body["reachable"] is False and body["error"] == "catalog: ConnectionError"


def test_llm_health_reports_missing_key(monkeypatch):
    monkeypatch.setattr(llm, "list_models", lambda: [{"id": settings.bharatcode_model, "metadata": {"toolCalling": True}}])
    monkeypatch.setattr(settings, "bharatcode_api_key", "")
    with TestClient(app) as c:
        body = c.get("/api/health/llm?live=true").json()
    assert body["model_listed"] is True and body["model_capabilities"] == {"toolCalling": True}
    assert body["live_inference"] is False and "not set" in body["error"]
