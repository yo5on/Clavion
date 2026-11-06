"""Upload validation, case isolation, privacy of the audit trail, and the editable appeal (SYNTHETIC data only)."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.demo import fixtures
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def new_case(c):
    return c.post("/api/cases", json={"title": "Security test"}).json()["id"]


def up(c, cid, doc_type, name, data):
    return c.post(f"/api/cases/{cid}/documents/{doc_type}", data={"provider": "local"}, files={"file": (name, data)})


def pdf(doc_type):
    return fixtures.render_pdf(fixtures.TEXTS[doc_type])


@pytest.mark.parametrize("name,data,msg", [
    ("bill.pdf", b"\x89PNG\r\n\x1a\nnot a pdf", "does not match"),
    ("bill.png", b"%PDF-1.4 fake", "does not match"),
    ("bill.pdf", b"%PDF-1.4\n garbage without objects", "could not read PDF"),
    ("bill.exe", b"MZ", "unsupported file type"),
    ("bill.txt", b"", "empty"),
    ("bill.txt", b"abc\x00def", "not plain text"),
])
def test_invalid_files_are_rejected(client, name, data, msg):
    r = up(client, new_case(client), "bill", name, data)
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_encrypted_pdf(client):
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(pdf("bill"))))
    w.encrypt("secret")
    buf = io.BytesIO()
    w.write(buf)
    r = up(client, new_case(client), "bill", "bill.pdf", buf.getvalue())
    assert r.status_code == 422 and "password-protected" in r.json()["detail"]


def test_decompression_bomb_is_refused(client):
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")  # tiny file, 81 megapixels
    r = up(client, new_case(client), "bill", "bill.png", buf.getvalue())
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_oversized_upload(client):
    r = up(client, new_case(client), "bill", "bill.txt", b"a" * (15 * 1024 * 1024 + 10))
    assert r.status_code == 422 and "15 MB" in r.json()["detail"]


def test_same_file_in_two_slots_is_refused(client):
    cid = new_case(client)
    assert up(client, cid, "bill", "bill.pdf", pdf("bill")).status_code == 200
    r = up(client, cid, "policy", "copy.pdf", pdf("bill"))
    assert r.status_code == 409 and "already uploaded as the hospital bill" in r.json()["detail"]


def test_wrong_slot_and_bad_encoding_warn(client):
    cid = new_case(client)
    r = up(client, cid, "policy", "x.pdf", pdf("bill"))
    assert any("reads like a hospital bill" in w for w in r.json()["documents"]["policy"]["provenance"]["warnings"])
    r = up(client, cid, "settlement", "s.txt", fixtures.SETTLEMENT_TEXT.encode() + b"\xff\xfe")
    assert any("not valid UTF-8" in w for w in r.json()["documents"]["settlement"]["provenance"]["warnings"])


def test_client_path_is_not_stored(client):
    r = up(client, new_case(client), "bill", "C:\\Users\\someone\\Desktop\\bill.pdf", pdf("bill"))
    assert r.json()["documents"]["bill"]["filename"] == "bill.pdf"


def test_case_isolation_and_delete(client):
    a, b = new_case(client), new_case(client)
    up(client, a, "bill", "bill.pdf", pdf("bill"))
    assert client.get(f"/api/cases/{b}").json()["documents"] == {}
    assert client.delete(f"/api/cases/{a}").status_code == 204
    assert client.get(f"/api/cases/{a}").status_code == 404
    assert client.delete(f"/api/cases/{a}").status_code == 404
    assert client.get(f"/api/cases/{'x' * 65}").status_code == 422


def audited_case(c):
    cid = new_case(c)
    for t in ("bill", "policy", "settlement"):
        assert up(c, cid, t, f"{t}.pdf", pdf(t)).status_code == 200
    return cid, c.post(f"/api/cases/{cid}/audit").json()


def test_corrections_are_marked_and_trail_holds_no_document_text(client):
    cid, body = audited_case(client)
    bill = body["documents"]["bill"]["data"]
    bill["line_items"][0]["amount"] = "26500.00"
    r = client.put(f"/api/cases/{cid}/documents/bill", json=bill).json()
    f = r["documents"]["bill"]["fields"]
    assert f["line_items.0"]["status"] == "corrected" and f["line_items.0"]["source"]["page"] == 1
    assert f["line_items.1"]["status"] == "extracted"
    assert r["audit"] is None  # the old audit no longer applies
    events = [e["event"] for e in r["trail"]]
    assert events[-1] == "document_corrected" and "audit_run" in events
    trail = str(r["trail"])
    for secret in ("Asha Verma", "SHP/2026/55501", "26500"):
        assert secret not in trail


def test_appeal_statements_are_typed_and_editable(client):
    cid, body = audited_case(client)
    sts = body["appeal"]["statements"]
    kinds = {s["kind"] for s in sts}
    assert {"source_fact", "calculation", "suggestion", "standard"} <= kinds
    assert all(s["refs"] for s in sts if s["kind"] in ("source_fact", "calculation"))
    letter = body["appeal"]["text"].lower()
    for word in ("unlawful", "illegal", "fraud", "you are entitled", "guarantee"):
        assert word not in letter

    drop = next(s for s in sts if s["kind"] == "suggestion")
    drop["include"] = False
    keep = next(s for s in sts if s["kind"] == "calculation")
    keep["text"], keep["edited"] = "EDITED CALCULATION STATEMENT", True
    r = client.put(f"/api/cases/{cid}/appeal", json={"statements": sts}).json()
    assert drop["text"] not in r["appeal"]["text"] and "EDITED CALCULATION STATEMENT" in r["appeal"]["text"]
    out = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(
        client.get(f"/api/cases/{cid}/export.pdf?kind=appeal").content)).pages)
    assert "EDITED CALCULATION STATEMENT" in out and drop["text"][:40] not in out


def test_export_is_not_cached(client):
    cid, _ = audited_case(client)
    assert client.get(f"/api/cases/{cid}/export.pdf").headers["cache-control"] == "no-store"
