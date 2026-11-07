"""End-to-end API workflow on SYNTHETIC documents, plus provider labelling."""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.demo import fixtures
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _upload(c, case_id, doc_type, provider="local", fmt="pdf"):
    data = fixtures.render_pdf(fixtures.TEXTS[doc_type]) if fmt == "pdf" else fixtures.render_png(fixtures.TEXTS[doc_type])
    return c.post(f"/api/cases/{case_id}/documents/{doc_type}", data={"provider": provider},
                  files={"file": (f"{doc_type}.{fmt}", data)})


def _pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def test_full_document_to_audit_workflow(client):
    case = client.post("/api/cases", json={"title": "Test claim"}).json()
    for doc_type in ("bill", "policy", "settlement"):
        r = _upload(client, case["id"], doc_type)
        assert r.status_code == 200, r.text
        prov = r.json()["documents"][doc_type]["provenance"]
        assert prov == {**prov, "provider": "local", "ai_generated": False, "demo": True, "text_method": "pdf-text"}

    r = client.post(f"/api/cases/{case['id']}/audit")
    assert r.status_code == 200
    body = r.json()
    audit = body["audit"]
    assert body["status"] == "audited" and body["demo"] is True
    assert audit["contestable_total"] == "4447.80" and audit["unverified_total"] == "2500.00"
    assert [f["status"] for f in audit["findings"]] == fixtures.EXPECTED["statuses"]
    assert "DEMO - SYNTHETIC DATA" in body["appeal"]["text"] and "Rs 4,447.80" in body["appeal"]["text"]
    assert "(no AI)" in body["appeal"]["source"]

    report = client.get(f"/api/cases/{case['id']}/export.pdf")
    assert report.status_code == 200 and report.headers["content-type"] == "application/pdf"
    text = _pdf_text(report.content)
    assert "DEMO - SYNTHETIC DATA" in text and "Rs 3,447.80" in text and "Clause 4.3" in text

    client.put(f"/api/cases/{case['id']}/appeal", json={"text": "Edited appeal text"})
    appeal = client.get(f"/api/cases/{case['id']}/export.pdf?kind=appeal")
    assert "Edited appeal text" in _pdf_text(appeal.content)

    listed = client.get("/api/cases").json()
    row = next(x for x in listed if x["id"] == case["id"])
    assert row["contestable_total"] == "4447.80" and row["documents"] == ["bill", "policy", "settlement"]


def test_manual_correction_changes_audit(client):
    case = client.post("/api/demo/case").json()
    assert case["audit"]["contestable_total"] == "4447.80"
    policy = case["documents"]["policy"]["data"]
    policy["non_payable_items"].append("Registration charges")  # user corrects the extracted list
    r = client.put(f"/api/cases/{case['id']}/documents/policy", json=policy)
    assert r.status_code == 200 and r.json()["audit"] is None  # stale audit is cleared
    assert r.json()["documents"]["policy"]["provenance"]["manually_corrected"] is True
    audit = client.post(f"/api/cases/{case['id']}/audit").json()["audit"]
    assert audit["contestable_total"] == "3447.80" and audit["findings"][4]["status"] == "supported"


def test_correction_is_validated(client):
    case = client.post("/api/demo/case").json()
    bad = {**case["documents"]["bill"]["data"], "line_items": [{"description": "x", "amount": "lots"}]}
    assert client.put(f"/api/cases/{case['id']}/documents/bill", json=bad).status_code == 422


def test_image_upload_uses_ocr(client):
    case = client.post("/api/cases", json={"title": "OCR"}).json()
    r = _upload(client, case["id"], "settlement", fmt="png")
    assert r.status_code == 200
    assert r.json()["documents"]["settlement"]["provenance"]["text_method"] == "image-ocr"
    assert r.json()["documents"]["settlement"]["data"]["approved_amount"] == "97069.62"


def test_audit_requires_settlement_and_upload_rejects_bad_types(client):
    case = client.post("/api/cases", json={"title": "x"}).json()
    assert client.post(f"/api/cases/{case['id']}/audit").status_code == 409
    r = client.post(f"/api/cases/{case['id']}/documents/bill", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 422
    assert client.get("/api/cases/nope").status_code == 404


def test_demo_provider_is_labelled_and_limited_to_fixtures(client):
    case = client.post("/api/cases", json={"title": "x"}).json()
    r = _upload(client, case["id"], "bill", provider="demo")
    assert r.status_code == 200
    prov = r.json()["documents"]["bill"]["provenance"]
    assert prov["provider"] == "demo" and prov["demo"] is True and prov["ai_generated"] is False
    other = client.post(f"/api/cases/{case['id']}/documents/bill", data={"provider": "demo"},
                        files={"file": ("real.txt", b"Room rent 1 x 1,000.00 = 1,000.00")})
    assert other.status_code == 409


def test_demo_documents_download(client):
    r = client.get("/api/demo/documents/policy")
    assert r.status_code == 200 and "SYNTHETIC TEST DOCUMENT" in _pdf_text(r.content)


def test_negative_or_out_of_range_corrections_are_rejected(client):
    case = client.post("/api/demo/case").json()
    letter = {**case["documents"]["settlement"]["data"], "approved_amount": "-1.00"}
    assert client.put(f"/api/cases/{case['id']}/documents/settlement", json=letter).status_code == 422
    policy = {**case["documents"]["policy"]["data"], "copay_percent": "120"}
    assert client.put(f"/api/cases/{case['id']}/documents/policy", json=policy).status_code == 422


def test_poor_scan_of_synthetic_document_is_still_labelled_demo(client):
    from .test_synthetic_cases import CASES, degraded_scan

    case = client.post("/api/cases", json={"title": "scan"}).json()
    r = client.post(f"/api/cases/{case['id']}/documents/bill", data={"provider": "local"},
                    files={"file": ("scan.png", degraded_scan(CASES["6_incomplete_poor_quality"]["bill"]))})
    assert r.status_code == 200 and r.json()["documents"]["bill"]["provenance"]["demo"] is True
