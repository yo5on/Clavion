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


def test_lakh_sum_insured_and_short_copay_wording():
    # "Rs 5 Lakh" = 5,00,000, so 1% = Rs 5,000/day (was read as Rs 5, giving a Rs 0.05/day limit).
    policy, _ = parsers.parse_policy("Sum Insured: Rs 5 Lakh\n3.1 Room Rent\nPayable up to 1% of Sum Insured per day."
                                     "\n5.1 Co-payment\nCo-pay of 20% applies to every claim.")
    assert policy.sum_insured == Decimal("500000") and policy.room_rent_limit_per_day == Decimal("5000.00")
    assert policy.copay_percent == Decimal("20")
    assert parsers.money("1.5 crore") == Decimal("15000000") and parsers.money("1,30,940.50") == Decimal("130940.50")


@pytest.mark.parametrize("s,value", [("Rs 5 Lakh", "500000"), ("5 lakh", "500000"), ("2 lakhs", "200000"),
                                     ("1.5 crore", "15000000"), ("1.5 Crore", "15000000"), ("3 lacs", "300000"),
                                     ("1,30,940.50", "130940.50"), ("26000", "26000"), ("4,800.00", "4800.00")])
def test_money_indian_formats(s, value):
    assert parsers.money(s.removeprefix("Rs ")) == Decimal(value)


def test_lakh_crore_in_policy_fields():
    policy, _ = parsers.parse_policy("Sum Insured: Rs 1.5 Crore\n3.1 Room Rent\nUp to Rs 1 lakh per day.\n"
                                     "4.4 Sub-limits\n- Cataract surgery: Rs 2 lakhs per eye")
    assert policy.sum_insured == Decimal("15000000")
    assert policy.room_rent_limit_per_day == Decimal("100000")
    assert [(s.name, s.limit) for s in policy.sub_limits] == [("Cataract surgery", Decimal("200000"))]


def test_ordinary_amounts_unchanged():
    policy, _ = parsers.parse_policy("Sum Insured: Rs 3,00,000\n3.1 Room Rent\nUp to Rs 5,000 per day.")
    assert (policy.sum_insured, policy.room_rent_limit_per_day) == (Decimal("300000"), Decimal("5000"))
    letter, _ = parsers.parse_settlement("Amount Claimed: Rs 1,30,940.50\nAmount Approved: Rs 97,069.62")
    assert (letter.claimed_amount, letter.approved_amount) == (Decimal("130940.50"), Decimal("97069.62"))


@pytest.mark.parametrize("wording,pct", [("Co-pay of 20% applies to every claim.", "20"),
                                         ("A co-payment of 15% applies to every claim.", "15"),
                                         ("A 20% co-pay applies to every claim.", "20")])
def test_unconditional_copay_wordings(wording, pct):
    policy, _ = parsers.parse_policy(f"5.1 Co-payment\n{wording}")
    assert policy.copay_percent == Decimal(pct) and policy.copay_condition is None and policy.copay_clause == "5.1"


CONDITIONAL_COPAY = "Co-payment: 10% where insured is aged 61 or above"


@pytest.mark.parametrize("text", [f"5.1 Co-payment\n{CONDITIONAL_COPAY}", f"5.1 {CONDITIONAL_COPAY}"])
def test_conditional_copay_keeps_condition(text):
    policy, _ = parsers.parse_policy(text)
    assert policy.copay_percent == Decimal("10") and policy.copay_clause == "5.1"
    assert policy.copay_condition == "where insured is aged 61 or above"


@pytest.mark.parametrize("text", [f"5.1 Co-payment\n{CONDITIONAL_COPAY}", f"5.1 {CONDITIONAL_COPAY}"])
def test_conditional_copay_needs_clarification_in_audit(text):
    from app.services.audit import run_audit

    policy, _ = parsers.parse_policy(text)
    letter = SettlementLetter(claimed_amount="1000.00", approved_amount="900.00",
                              deductions=[{"description": "Co-payment 10%", "amount": "100.00"}])
    bill = HospitalBill(line_items=[{"description": "Room rent", "amount": "1000.00"}])
    f = run_audit(bill, policy, letter).findings[0]
    # not "supported": the patient's age is not in the documents, so the copay is not universally applicable
    assert f.status == "unverified" and f.supported_amount is None and "aged 61" in f.explanation


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
