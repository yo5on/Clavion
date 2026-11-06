from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_db_ocr_and_local_method():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] is True and body["ocr_available"] is True
    assert "no AI" in body["analysis"]


def test_no_external_ai_endpoints_are_exposed():
    with TestClient(app) as c:
        paths = c.get("/openapi.json").json()["paths"]
        providers = {p["id"]: p for p in c.get("/api/providers").json()}
    assert not any("llm" in p or "bharatcode" in p for p in paths)
    assert set(providers) == {"local", "demo"} and not any(p["ai"] for p in providers.values())
