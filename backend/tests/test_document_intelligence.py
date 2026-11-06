"""Parser and provenance tests on small SYNTHETIC texts: every value must come with its status and source line."""

from decimal import Decimal as D

from app.services.documents import guess_type
from app.services.parsers import extract_bill, extract_policy, extract_settlement, parse_date

BILL = "\n".join([
    "*** SYNTHETIC TEST DOCUMENT ***", "Arogya Hospital", "FINAL BILL", "Patient Name: Meera Rao",
    "Date of Admission: 02/09/2026    Date of Discharge: 05-Sep-2026", "",
    " 1. Room rent                    3 x  4,000/- =  12,000/-",
    "    Page total                                  12,000.00",
    "\f*** SYNTHETIC TEST DOCUMENT ***", "",
    " 2. Pharmacy                     1 x  2,500.50 =  2,500.50",
    "", "    GRAND TOTAL (Rs)  14,500.50"])


def test_bill_amounts_dates_and_page_sources():
    x = extract_bill(BILL)
    b = x.doc
    assert [(i.description, i.amount) for i in b.line_items] == [("Room rent", D("12000.00")), ("Pharmacy", D("2500.50"))]
    assert b.total_amount == D("14500.50")  # the page total is not taken as the grand total
    assert (str(b.admission_date), str(b.discharge_date)) == ("02/09/2026", "05-Sep-2026")
    # line 2 is on page 2, third line (blank lines counted)
    src = x.fields["line_items.1"].source
    assert (src.page, src.line) == (2, 3) and "Pharmacy" in src.text
    assert x.fields["total_amount"].status == "extracted" and x.fields["total_amount"].source.page == 2
    assert x.fields["patient_name"].source.line == 4
    assert x.fields["bill_number"].status == "missing"  # never guessed
    assert x.fields["hospital_name"].status == "inferred"  # picked heuristically, and said so


def test_day_first_dates():
    assert str(parse_date("03/04/2026")) == "2026-04-03"
    assert str(parse_date("12-Oct-2026")) == "2026-10-12"
    assert parse_date("not a date") is None


def test_table_format_settlement_and_paid_amount():
    text = "\n".join(["Claim No: X/1", "Amount Claimed: Rs 10,000.00", "",
                      "Description   Claimed     Approved    Deducted   Reason",
                      "Room Rent     6,000.00    4,000.00    2,000.00   Room rent capping as per Clause 3.1",
                      "Pharmacy      4,000.00    4,000.00        0.00",
                      "", "Amount Approved: Rs 8,000.00", "Amount Paid: Rs 7,900.00"])
    x = extract_settlement(text)
    s = x.doc
    assert [(d.description, d.amount, d.clause_ref) for d in s.deductions] == [
        ("Room Rent - Room rent capping as per Clause 3.1", D("2000.00"), "3.1")]  # zero-deduction rows are skipped
    assert (s.claimed_amount, s.approved_amount, s.paid_amount) == (D("10000.00"), D("8000.00"), D("7900.00"))
    assert x.fields["deductions.0"].source.line == 5


def test_deduction_line_without_amount_is_reported_not_dropped_silently():
    text = "\n".join(["Amount Claimed: Rs 5,000.00", "Deductions:", "1. Room rent above limit  Rs 1,000.00",
                      "2. Non-payable items as per annexure", "Amount Approved: Rs 4,000.00"])
    x = extract_settlement(text)
    assert len(x.doc.deductions) == 1
    assert any("Non-payable items as per annexure" in w for w in x.warnings)


def test_rs_without_decimals():
    x = extract_settlement("Amount Claimed: Rs 5000\nDeductions:\n1. Co-payment 10%  Rs 500\nAmount Approved: Rs 4500")
    assert [d.amount for d in x.doc.deductions] == [D("500.00")]


POLICY = """*** SYNTHETIC TEST DOCUMENT ***
Policy No: P/77
Sum Insured: Rs 3,00,000

3.1 Room Rent
Room rent is payable up to a single private room.

8.1 Permanent Exclusions
- Dental treatment
- Spectacles
"""


def test_policy_room_category_and_exclusions_with_sources():
    x = extract_policy(POLICY)
    p = x.doc
    assert p.room_rent_limit_per_day is None and "single private room" in p.room_rent_category
    assert p.exclusions == ["Dental treatment", "Spectacles"] and p.exclusions_clause == "8.1"
    assert x.fields["sum_insured"].source.line == 3
    assert x.fields["copay_percent"].status == "missing"


def test_percent_limit_lower_than_cap_is_inferred():
    text = "Sum Insured: Rs 2,00,000\n\n3.1 Room Rent\nRoom rent up to 1% of the Sum Insured per day, maximum Rs 5,000 per day.\n"
    x = extract_policy(text)
    # 1% of 2,00,000 = 2,000 < 5,000: the lower figure applies, and it is a derived value
    assert x.doc.room_rent_limit_per_day == D("2000")
    assert x.fields["room_rent_limit_per_day"].status == "inferred"


def test_guess_type():
    assert guess_type(BILL) == "bill"
    assert guess_type(POLICY + "\nPolicy Wording\nThe Company shall indemnify\n") == "policy"
    assert guess_type("CLAIM SETTLEMENT LETTER\nAmount Approved: Rs 1.00\nDeductions:") == "settlement"
    assert guess_type("hello") is None
