"""Co-pay reconciliation (R-COPAY-01) on SYNTHETIC documents built in code.

Every expected amount is worked out by hand in the comment next to it, independently of the engine. Rules tested:
- the co-pay base is read from the clause wording ("admissible" -> after other deductions; "total claim amount" ->
  before them); wording naming no base, or both, is ambiguous and is not resolved;
- other deductions leave the base only at CLAVION's own figure (the lower of insurer and CLAVION), never at an
  insurer figure CLAVION could not establish;
- conditional co-pay stays unverified; the excess over the largest possible co-pay is contestable.
"""

from decimal import Decimal as D

import pytest

from app.schemas.bill import BillLineItem, HospitalBill
from app.schemas.claim import PolicyClause, PolicyDocument, SettlementLetter, SubLimit
from app.services.audit import run_audit

ADMISSIBLE = "A 10% co-payment applies to every admissible claim."


def item(desc, qty, rate, cat=None):
    q, r = D(str(qty)), D(rate)
    return BillLineItem(description=desc, quantity=q, unit_price=r, amount=q * r, category=cat)


def policy(copay_text=ADMISSIBLE, pct="10", condition=None):
    clauses = [PolicyClause(id="3.1", title="Room Rent", text="3.1 Room Rent\nRoom rent up to Rs 5,000 per day."),
               PolicyClause(id="4.4", title="Sub-limits", text="4.4 Sub-limits\n- Cataract surgery: Rs 40,000"),
               PolicyClause(id="5.1", title="Co-payment", text=f"5.1 Co-payment\n{copay_text}"),
               PolicyClause(id="6.1", title="Non-payable Items", text="6.1 Non-payable Items\n- Gloves"),
               PolicyClause(id="8.1", title="Exclusions", text="8.1 Exclusions\n- Dental treatment")]
    return PolicyDocument(room_rent_limit_per_day="5000", room_rent_clause="3.1",
                          sub_limits=[SubLimit(name="Cataract surgery", limit="40000", clause_id="4.4")],
                          copay_percent=pct, copay_clause="5.1", copay_condition=condition,
                          non_payable_items=["Gloves"], non_payable_clause="6.1",
                          exclusions=["Dental treatment"], exclusions_clause="8.1", clauses=clauses)


def audit(bill_items, deds, claimed, pol=None):
    letter = SettlementLetter(claimed_amount=claimed, deductions=[{"description": d, "amount": a} for d, a in deds])
    return run_audit(HospitalBill(line_items=bill_items), pol or policy(), letter)


def copay(r):
    f = next(f for f in r.findings if f.rule_id == "R-COPAY-01")
    # transparent trace on every co-pay finding: both sides' figures are shown
    assert any(s.startswith("Claimed amount (settlement letter)") for s in f.calculation)
    assert any(s.startswith("Insurer's co-pay (settlement letter)") for s in f.calculation)
    return f


def triple(f):
    return f.status, f.supported_amount, f.contestable_amount


SURGERY = [item("Surgeon fee", 1, "100000.00")]


# ------------------------------------------------------------------ unconditional

def test_unconditional_copay():
    # 10% x 1,00,000 = 10,000
    f = copay(audit(SURGERY, [("Co-payment 10%", "10000.00")], "100000.00"))
    assert triple(f) == ("supported", D("10000.00"), D("0.00"))
    assert any("'admissible' amount" in s for s in f.calculation)


def test_copay_on_total_claim_wording_uses_gross():
    # "on the total claim amount": base = claimed 1,00,000 even after a 20,000 exclusion; 10% = 10,000
    bill = [item("Surgery", 1, "80000.00"), item("Dental treatment", 1, "20000.00")]
    pol = policy("A 10% co-payment applies on the total claim amount.")
    f = copay(audit(bill, [("Excluded - Dental treatment", "20000.00"), ("Co-payment", "10000.00")], "100000.00", pol))
    assert triple(f) == ("supported", D("10000.00"), D("0.00"))


# ------------------------------------------------------------------ conditional

def test_conditional_copay_is_unverified_with_trace():
    pol = policy(condition="where the Insured Person is aged 61 years or above")
    f = copay(audit(SURGERY, [("Co-payment 10%", "10000.00")], "100000.00", pol))
    assert (f.status, f.supported_amount) == ("unverified", None)
    assert "If met, up to ₹10,000.00" in f.explanation
    assert any(c.met is None and "aged 61" in c.text for c in f.conditions)


def test_conditional_copay_stays_unverified_even_above_maximum():
    # 15,000 exceeds 10% x 1,00,000 = 10,000, but eligibility is unknown: preserved as unverified
    pol = policy(condition="where the Insured Person is aged 61 years or above")
    f = copay(audit(SURGERY, [("Co-payment 10%", "15000.00")], "100000.00", pol))
    assert f.status == "unverified"


# ------------------------------------------------------------------ insurer over-deducting elsewhere

ROOM_BILL = [item("Room rent", 4, "6000.00", "room_rent"), item("Surgeon fee", 1, "76000.00")]


@pytest.mark.parametrize("room_ded", ["4000.00", "14000.00"])
def test_insurer_overdeduction_elsewhere_does_not_move_copay(room_ded):
    # Room excess = (6,000 - 5,000) x 4 = 4,000 whatever the insurer deducted.
    # Base = 1,00,000 - 4,000 = 96,000; co-pay 10% = 9,600 in both cases.
    r = audit(ROOM_BILL, [("Room rent above limit", room_ded), ("Co-payment 10%", "9600.00")], "100000.00")
    f = copay(r)
    assert triple(f) == ("supported", D("9600.00"), D("0.00"))
    assert any(f"insurer ₹{D(room_ded):,}" in s and "CLAVION ₹4,000.00" in s for s in f.calculation)


def test_insurer_copay_on_overdeducted_base_is_lower_not_contested():
    # Insurer: room 14,000 (CLAVION 4,000), co-pay 10% x 86,000 = 8,600. CLAVION co-pay 9,600 > 8,600: the insurer
    # deducted less co-pay, so the co-pay is supported; the 10,000 room excess is contested on its own finding.
    r = audit(ROOM_BILL, [("Room rent above limit", "14000.00"), ("Co-payment 10%", "8600.00")], "100000.00")
    room, f = r.findings
    assert triple(room) == ("contestable", D("4000.00"), D("10000.00"))
    assert triple(f) == ("supported", D("9600.00"), D("0.00"))


def test_copay_listed_before_other_deductions_still_uses_them():
    # Same as above with the co-pay first on the letter: base still 96,000 -> 9,600
    r = audit(ROOM_BILL, [("Co-payment 10%", "9600.00"), ("Room rent above limit", "4000.00")], "100000.00")
    assert triple(copay(r)) == ("supported", D("9600.00"), D("0.00")) and r.findings[0].rule_id == "R-COPAY-01"


# ------------------------------------------------------------------ exclusions, sub-limits, room rent

def test_exclusion_combined_with_copay():
    # Dental 20,000 excluded (on list). Base = 1,00,000 - 20,000 = 80,000; 10% = 8,000.
    # Insurer took 10% of 1,00,000 = 10,000 -> 2,000 contestable (co-pay charged on the excluded amount too)
    bill = [item("Surgery", 1, "80000.00"), item("Dental treatment", 1, "20000.00")]
    f = copay(audit(bill, [("Excluded - Dental treatment", "20000.00"), ("Co-payment 10%", "10000.00")], "100000.00"))
    assert triple(f) == ("contestable", D("8000.00"), D("2000.00"))
    assert "applied before the other deductions" in f.contestable_reason


def test_sublimit_combined_with_copay():
    # Cataract 55,000 vs sub-limit 40,000 -> 15,000. Base = 60,000 - 15,000 = 45,000; 10% = 4,500
    bill = [item("Cataract surgery package", 1, "55000.00"), item("Consultation", 1, "5000.00")]
    f = copay(audit(bill, [("Amount above cataract sub-limit", "15000.00"), ("Co-payment 10%", "4500.00")], "60000.00"))
    assert triple(f) == ("supported", D("4500.00"), D("0.00"))


def test_room_rent_combined_with_copay():
    # Room 3 x 7,000 = 21,000; excess (7,000 - 5,000) x 3 = 6,000. Claimed 50,000; base 44,000; 10% = 4,400.
    # Insurer 5,000 (10% of 50,000) -> 600 contestable
    bill = [item("Room rent", 3, "7000.00", "room_rent"), item("Surgeon fee", 1, "29000.00")]
    f = copay(audit(bill, [("Room rent above limit", "6000.00"), ("Co-payment 10%", "5000.00")], "50000.00"))
    assert triple(f) == ("contestable", D("4400.00"), D("600.00"))


# ------------------------------------------------------------------ missing or ambiguous policy information

def test_no_policy_is_unverified():
    letter = SettlementLetter(claimed_amount="1000.00", deductions=[{"description": "Co-payment", "amount": "100.00"}])
    assert run_audit(HospitalBill(line_items=[]), None, letter).findings[0].status == "unverified"


def test_missing_claimed_amount_is_unverified():
    f = audit(SURGERY, [("Co-payment 10%", "10000.00")], None).findings[0]
    assert f.status == "unverified" and any("Claimed amount" in m for m in f.missing)


@pytest.mark.parametrize("wording", ["A 10% co-payment applies.",
                                     "A 10% co-payment applies to the admissible amount or the total claim amount."])
def test_ambiguous_base_needs_clarification(wording):
    # No base named (or both named): CLAVION does not choose. Exclusion 20,000 established.
    # On claimed: 10% x 1,00,000 = 10,000; after deductions: 10% x 80,000 = 8,000. Insurer 9,000 is within both.
    bill = [item("Surgery", 1, "80000.00"), item("Dental treatment", 1, "20000.00")]
    r = audit(bill, [("Excluded - Dental treatment", "20000.00"), ("Co-payment", "9000.00")], "100000.00",
              policy(wording))
    f = copay(r)
    assert (f.status, f.supported_amount, f.basis) == ("unverified", None, "insufficient")
    assert any("₹10,000.00" in s and "₹8,000.00" in s for s in f.calculation)
    assert any("Clarification of the amount Clause 5.1" in q for q in r.documents_to_request)


def test_ambiguous_base_excess_over_largest_reading_is_contestable():
    # Largest reading = 10% x 50,000 = 5,000. Insurer 6,000 -> 1,000 contestable on any reading
    f = copay(audit([item("Surgeon fee", 1, "50000.00")], [("Co-payment", "6000.00")], "50000.00",
                    policy("A 10% co-payment applies.")))
    assert triple(f) == ("contestable", D("5000.00"), D("1000.00"))


def test_unestablished_other_deduction_leaves_copay_unverified():
    # "Non-payable - Masks" 10,000 has no bill line, so CLAVION cannot establish it and does not remove it.
    # Largest co-pay = 10% x 50,000 = 5,000; insurer 4,000 (10% of 40,000) cannot be confirmed -> unverified
    r = audit([item("Surgeon fee", 1, "50000.00")], [("Non-payable items - Masks", "10000.00"),
                                                    ("Co-payment 10%", "4000.00")], "50000.00")
    f = copay(r)
    assert (f.status, f.supported_amount) == ("unverified", None)
    assert "at most ₹5,000.00" in f.explanation
    assert any("Deduction 1" in s and "could not establish" in s for s in f.calculation)


def test_unestablished_other_deduction_excess_over_maximum_is_contestable():
    # As above, insurer co-pay 6,000 > largest possible 5,000 -> 1,000 contestable
    r = audit([item("Surgeon fee", 1, "50000.00")], [("Non-payable items - Masks", "10000.00"),
                                                    ("Co-payment 10%", "6000.00")], "50000.00")
    assert triple(copay(r)) == ("contestable", D("5000.00"), D("1000.00"))


# ------------------------------------------------------------------ zero and boundary amounts

@pytest.mark.parametrize("pct,claimed,insurer,expected", [
    ("0", "50000.00", "0.00", ("supported", D("0.00"), D("0.00"))),          # 0% x 50,000 = 0
    ("0", "50000.00", "100.00", ("contestable", D("0.00"), D("100.00"))),    # 0% allows nothing
    ("100", "1000.00", "1000.00", ("supported", D("1000.00"), D("0.00"))),   # 100% x 1,000 = 1,000
    ("10", "0.00", "0.00", ("supported", D("0.00"), D("0.00"))),             # nothing claimed
    ("12.5", "33333.33", "4166.67", ("supported", D("4166.67"), D("0.00"))),  # 4,166.66625 -> 4,166.67
    ("10", "33333.33", "3334.33", ("supported", D("3333.33"), D("0.00"))),   # 1.00 over: within rounding
    ("10", "33333.33", "3334.34", ("contestable", D("3333.33"), D("1.01"))),  # 1.01 over: contestable
])
def test_zero_and_boundary(pct, claimed, insurer, expected):
    f = copay(audit([item("Surgeon fee", 1, claimed)], [("Co-payment", insurer)], claimed,
                    policy(f"A {pct}% co-payment applies to every admissible claim.", pct)))
    assert triple(f) == expected


def test_base_never_negative():
    # Exclusion 20,000 established against a 15,000 claim: base = max(15,000 - 20,000, 0) = 0 -> co-pay 0
    bill = [item("Dental treatment", 1, "20000.00")]
    f = copay(audit(bill, [("Excluded - Dental treatment", "20000.00"), ("Co-payment", "0.00")], "15000.00"))
    assert triple(f) == ("supported", D("0.00"), D("0.00"))
