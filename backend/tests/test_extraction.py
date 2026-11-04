"""Extraction and validation on SYNTHETIC documents with known ground truth."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo import fixtures
from app.schemas.bill import HospitalBill
from app.schemas.claim import SettlementLetter
from app.services import documents, parsers


@pytest.mark.parametrize("doc_type", ["bill", "policy", "settlement"])
def test_pdf_text_extraction_matches_ground_truth(doc_type):
    text, method, warnings = documents.extract_text(f"{doc_type}.pdf", fixtures.render_pdf(fixtures.TEXTS[doc_type]))
    doc, parse_warnings = getattr(parsers, f"parse_{doc_type}")(text)
    assert method == "pdf-text" and warnings == [] and parse_warnings == []
    assert doc == fixtures.ground_truth(doc_type)


def test_image_ocr_recovers_bill_amounts():
    text, method, _ = documents.extract_text("bill.png", fixtures.render_png(fixtures.BILL_TEXT))
    bill, warnings = parsers.parse_bill(text)
    assert method == "image-ocr" and warnings == []
    assert [it.amount for it in bill.line_items] == [Decimal(a) for _, _, _, a, _ in fixtures.BILL_ITEMS]
    assert [it.quantity for it in bill.line_items] == [q for _, q, _, _, _ in fixtures.BILL_ITEMS]
    assert bill.total_amount == fixtures.BILL_TOTAL and bill.bill_number == "SMH/IP/2026/004521"


def test_image_ocr_recovers_settlement_deductions():
    text, _, _ = documents.extract_text("letter.png", fixtures.render_png(fixtures.SETTLEMENT_TEXT))
    letter, _ = parsers.parse_settlement(text)
    truth = fixtures.ground_truth("settlement")
    assert [d.amount for d in letter.deductions] == [d.amount for d in truth.deductions]
    assert [d.clause_ref for d in letter.deductions] == [d.clause_ref for d in truth.deductions]
    assert (letter.claimed_amount, letter.approved_amount) == (truth.claimed_amount, truth.approved_amount)


def test_policy_clauses_and_terms():
    policy, _ = parsers.parse_policy(fixtures.POLICY_TEXT)
    assert [c.id for c in policy.clauses] == ["preamble", "1", "4.1", "4.2", "4.3", "4.4", "5.1", "7.2"]
    assert policy.clause("4.3").title == "Proportionate Deduction"
    assert (policy.room_rent_limit_per_day, policy.icu_limit_per_day) == (Decimal("5000"), Decimal("10000"))


def test_percent_only_room_rent_limit_uses_sum_insured():
    policy, _ = parsers.parse_policy("Sum Insured: Rs 3,00,000\n3.1 Room Rent\nPayable up to 1% of Sum Insured per day.")
    assert policy.room_rent_limit_per_day == Decimal("3000.00") and policy.room_rent_clause == "3.1"


def test_unparseable_text_is_flagged_not_invented():
    bill, warnings = parsers.parse_bill("hello world")
    assert bill.line_items == [] and bill.total_amount is None
    assert any("no line items" in w for w in warnings)
    letter, warnings = parsers.parse_settlement("nothing here")
    assert letter.deductions == [] and letter.approved_amount is None and len(warnings) == 3


def test_bill_arithmetic_issues_are_reported():
    bill, warnings = parsers.parse_bill("Room rent 2 x 1,000.00 = 2,500.00\nGRAND TOTAL 3,000.00")
    assert any("2 x 1000.00" in w for w in warnings) and any("total says 3000.00" in w for w in warnings)


@pytest.mark.parametrize("desc,cat", [("Room rent - Deluxe", "room_rent"), ("ICU charges", "icu"),
                                      ("Surgeon fee", "professional"), ("PPE kit", "consumables"),
                                      ("CT scan", "diagnostics"), ("Registration fee", "admin"),
                                      ("Something else", "other")])
def test_categorize(desc, cat):
    assert parsers.categorize(desc) == cat


def test_validation_rejects_bad_money():
    with pytest.raises(ValidationError):
        HospitalBill(line_items=[{"description": "x", "amount": "abc"}])
    assert SettlementLetter(claimed_amount="Rs 1,30,940.50").claimed_amount == Decimal("130940.50")


@pytest.mark.parametrize("name,data", [("x.exe", b"MZ"), ("x.pdf", b""), ("x.pdf", b"not a pdf")])
def test_rejects_bad_files(name, data):
    with pytest.raises(documents.DocumentError):
        documents.extract_text(name, data)
