"""Unit tests for individual audit rules and consistency checks, on small SYNTHETIC documents built in code.
Every expected amount is worked out by hand in the comment next to it."""

from decimal import Decimal as D

import pytest

from app.schemas.bill import BillLineItem, HospitalBill
from app.schemas.claim import PolicyClause, PolicyDocument, SettlementLetter, SubLimit
from app.services.audit import classify_deduction, run_audit
from app.services.rules import RULES, ROUNDING_TOLERANCE


def item(desc, qty, rate, cat=None):
    q, r = D(str(qty)), D(rate)
    return BillLineItem(description=desc, quantity=q, unit_price=r, amount=q * r, category=cat)


def letter(*deds, claimed=None, approved=None, **kw):
    return SettlementLetter(claimed_amount=claimed, approved_amount=approved, deductions=[
        {"description": d, "amount": a, "clause_ref": c} for d, a, c in deds], **kw)


CLAUSES = [PolicyClause(id="3.1", title="Room Rent", text="3.1 Room Rent\nRoom rent up to Rs 5,000 per day."),
           PolicyClause(id="3.2", title="ICU", text="3.2 ICU\nICU up to Rs 10,000 per day."),
           PolicyClause(id="3.3", title="Proportionate Deduction", text="3.3 Proportionate Deduction\n..."),
           PolicyClause(id="5.1", title="Co-payment", text="5.1 Co-payment\nA 10% co-payment applies."),
           PolicyClause(id="6.1", title="Non-payable Items", text="6.1 Non-payable Items\n- Gloves\n- Masks"),
           PolicyClause(id="8.1", title="Exclusions", text="8.1 Exclusions\n- Dental treatment")]
POLICY = PolicyDocument(policy_number="P/1", sum_insured="500000", room_rent_limit_per_day="5000",
                        room_rent_clause="3.1", icu_limit_per_day="10000", icu_clause="3.2",
                        proportionate_clause="3.3", proportionate_exclusions=["pharmacy", "diagnostics"],
                        copay_percent="10", copay_clause="5.1", non_payable_items=["Gloves", "Masks"],
                        non_payable_clause="6.1", exclusions=["Dental treatment"], exclusions_clause="8.1",
                        clauses=CLAUSES)


def one(bill, ded, policy=POLICY, **kw):
    return run_audit(bill, policy, letter(ded, **kw)).findings[0]


# ------------------------------------------------------------------ rule registry

def test_every_rule_is_explicit_and_unique():
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids)) and all(r.id.startswith("R-") for r in RULES)
    for r in RULES:
        assert r.title and r.supported_when and r.kind
        assert r.requires or r.kind == "unspecified"


@pytest.mark.parametrize("text,kind", [
    ("Room rent above limit", "room_rent_excess"), ("ICU charges in excess", "icu_excess"),
    ("Proportionate deduction", "proportionate"), ("Co-payment 10%", "copay"), ("Amount above sub-limit", "sublimit"),
    ("Excluded - dental treatment", "exclusion"), ("Non-payable items - gloves", "non_payable"),
    ("As per terms and conditions", "unspecified")])
def test_classification(text, kind):
    assert classify_deduction(text) == kind


# ------------------------------------------------------------------ R-ROOM-01

def test_room_rent_is_recalculated_line_by_line():
    """Regression: averaging two room rates hid the excess. 2 days at 3,000 + 2 days at 7,000, limit 5,000:
    average 5,000 -> 0 excess (wrong); per line (7,000 - 5,000) x 2 = 4,000.00 (right)."""
    bill = HospitalBill(line_items=[item("Room rent - ward", 2, "3000.00"), item("Room rent - deluxe", 2, "7000.00")])
    f = one(bill, ("Room rent above eligible limit", "4000.00", None))
    assert (f.status, f.supported_amount, f.contestable_amount) == ("supported", D("4000.00"), D("0.00"))
    assert f.rule_id == "R-ROOM-01" and any("Total excess = Rs 4,000.00" in s for s in f.calculation)


def test_room_rent_within_limit_is_contestable_with_reason():
    bill = HospitalBill(line_items=[item("Room rent", 3, "4500.00")])
    f = one(bill, ("Room rent above limit", "1500.00", None))
    assert (f.status, f.contestable_amount) == ("contestable", D("1500.00"))
    assert "within the Rs 5,000.00/day limit" in f.contestable_reason
    assert [c.met for c in f.conditions] == [True, True, False]


def test_room_category_limit_cannot_be_recalculated():
    policy = POLICY.model_copy(update={"room_rent_limit_per_day": None, "room_rent_category": "single private room"})
    f = one(HospitalBill(line_items=[item("Room rent", 2, "6000.00")]), ("Room rent capping", "2000.00", None), policy)
    assert f.status == "unverified" and f.supported_amount is None and "single private room" in f.explanation
    assert any("eligible room rent" in m for m in run_audit(
        HospitalBill(line_items=[]), policy, letter(("Room rent capping", "2000.00", None))).documents_to_request)


def test_room_rent_without_days_is_unverified():
    bill = HospitalBill(line_items=[{"description": "Room rent", "amount": "12000.00"}])
    f = one(bill, ("Room rent above limit", "2000.00", None))
    assert f.status == "unverified" and f.conditions[-1].met is False and f.missing


# ------------------------------------------------------------------ R-ICU-01

def test_icu_excess():
    # (12,500 - 10,000) x 2 = 5,000.00
    f = one(HospitalBill(line_items=[item("ICU charges", 2, "12500.00")]), ("ICU charges in excess", "5000.00", None))
    assert (f.rule_id, f.status, f.supported_amount) == ("R-ICU-01", "supported", D("5000.00"))


# ------------------------------------------------------------------ R-PROP-01

def prop_bill():
    # room 8,000/day, limit 5,000 -> ratio 0.625. Associated: surgeon 40,000. Exempt: pharmacy 8,000.
    return HospitalBill(line_items=[item("Room rent", 2, "8000.00"), item("Surgeon fee", 1, "40000.00"),
                                    item("Pharmacy", 1, "8000.00")])


def test_proportionate_recalculated_on_associated_charges_only():
    # 40,000 x (1 - 0.625) = 15,000.00
    f = one(prop_bill(), ("Proportionate deduction", "15000.00", None))
    assert (f.status, f.supported_amount) == ("supported", D("15000.00"))


def test_proportionate_explains_exempt_categories_the_insurer_included():
    # Insurer: (40,000 + 8,000) x 0.375 = 18,000.00 -> 3,000.00 contestable, reproduced by adding pharmacy
    f = one(prop_bill(), ("Proportionate deduction", "18000.00", None))
    assert (f.status, f.contestable_amount) == ("contestable", D("3000.00"))
    assert "reproduced exactly" in f.contestable_reason and "pharmacy" in f.contestable_reason


def test_proportionate_with_two_room_rates_is_unverified():
    bill = HospitalBill(line_items=[item("Room rent - ward", 1, "4000.00"), item("Room rent - deluxe", 1, "8000.00"),
                                    item("Surgeon fee", 1, "40000.00")])
    f = one(bill, ("Proportionate deduction", "10000.00", None))
    assert f.status == "unverified" and "more than one room rate" in f.explanation


def test_proportionate_when_room_within_limit_supports_nothing():
    bill = HospitalBill(line_items=[item("Room rent", 2, "4000.00"), item("Surgeon fee", 1, "40000.00")])
    f = one(bill, ("Proportionate deduction", "5000.00", None))
    assert (f.supported_amount, f.contestable_amount) == (D("0.00"), D("5000.00"))
    assert "within the policy limit" in f.contestable_reason


def test_proportionate_without_clause_is_contestable_on_absence():
    policy = POLICY.model_copy(update={"proportionate_clause": None})
    f = one(prop_bill(), ("Proportionate deduction", "15000.00", None), policy)
    assert (f.status, f.basis, f.contestable_amount) == ("contestable", "clause_absent", D("15000.00"))
    assert "confirm the policy document is complete" in f.contestable_reason


# ------------------------------------------------------------------ rounding tolerance

@pytest.mark.parametrize("insurer,status,cont", [
    ("15000.60", "supported", "0.00"),  # 0.60 over the recalculation: rounding
    ("15001.00", "supported", "0.00"),  # exactly the tolerance
    ("15001.50", "contestable", "1.50"),  # beyond it: the whole difference is contestable
])
def test_rounding_tolerance(insurer, status, cont):
    assert ROUNDING_TOLERANCE == D("1.00")
    f = one(prop_bill(), ("Proportionate deduction", insurer, None))
    assert (f.status, f.contestable_amount, f.supported_amount) == (status, D(cont), D("15000.00"))
    if status == "supported":
        assert "within rounding" in f.explanation


# ------------------------------------------------------------------ R-COPAY-01

def test_copay_applied_to_gross_claim_is_identified():
    # admissible = 50,000 - 10,000 = 40,000; 10% = 4,000. Insurer took 10% of 50,000 = 5,000 -> 1,000 contestable
    bill = HospitalBill(line_items=[item("Surgeon fee", 1, "50000.00")])
    r = run_audit(bill, POLICY, letter(("Non-payable items - Masks", "10000.00", None), ("Co-payment 10%", "5000.00", None),
                                       claimed="50000.00", approved="35000.00"))
    f = r.findings[1]
    assert (f.status, f.supported_amount, f.contestable_amount) == ("contestable", D("4000.00"), D("1000.00"))
    assert "applied before the other deductions" in f.contestable_reason


def test_copay_without_clause():
    policy = POLICY.model_copy(update={"copay_percent": None, "copay_clause": None})
    f = one(HospitalBill(line_items=[]), ("Co-payment", "500.00", None), policy, claimed="5000.00")
    assert (f.status, f.basis, f.contestable_amount) == ("contestable", "clause_absent", D("500.00"))


def test_copay_without_claimed_amount_is_unverified():
    f = one(HospitalBill(line_items=[]), ("Co-payment", "500.00", None))
    assert f.status == "unverified" and any("Claimed amount" in m for m in f.missing)


# ------------------------------------------------------------------ R-SUBLIMIT-01

def test_sublimit_that_matches_nothing():
    policy = POLICY.model_copy(update={"sub_limits": [SubLimit(name="Cataract surgery", limit="40000", clause_id="4.4")]})
    f = one(HospitalBill(line_items=[item("Knee replacement", 1, "200000.00")]),
            ("Amount above sub-limit", "50000.00", None), policy)
    assert (f.status, f.basis, f.supported_amount) == ("contestable", "clause_absent", D("0.00"))


# ------------------------------------------------------------------ R-NONPAY-01 / R-EXCL-01

def test_non_payable_listed_unlisted_and_unbilled():
    bill = HospitalBill(line_items=[item("Gloves", 1, "300.00"), item("Nebulizer kit", 1, "900.00")])
    r = run_audit(bill, POLICY, letter(("Non-payable - Gloves", "300.00", None),
                                       ("Non-payable - Nebulizer kit", "900.00", None),
                                       ("Non-payable - Masks", "200.00", None)))
    assert [f.status for f in r.findings] == ["supported", "contestable", "unverified"]
    assert r.findings[2].missing == ["No bill line found for 'Non-payable - Masks'"]


def test_exclusion_rule():
    bill = HospitalBill(line_items=[item("Dental treatment - filling", 1, "3000.00"), item("Hearing aid", 1, "9000.00")])
    r = run_audit(bill, POLICY, letter(("Excluded - Dental treatment", "3000.00", None),
                                       ("Excluded - Hearing aid", "9000.00", None)))
    assert [(f.rule_id, f.status) for f in r.findings] == [("R-EXCL-01", "supported"), ("R-EXCL-01", "contestable")]
    assert r.findings[1].policy_clause == "Clause 8.1 (Exclusions)"


# ------------------------------------------------------------------ R-UNSPEC-01 and the eight questions

def test_unspecified_asks_for_clause_and_calculation():
    r = run_audit(HospitalBill(line_items=[]), POLICY, letter(("As per policy terms", "2500.00", None)))
    f = r.findings[0]
    assert (f.rule_id, f.status, f.basis) == ("R-UNSPEC-01", "unverified", "no_reason")
    assert "clause and the calculation" in f.next_step
    assert any("As per policy terms" in x for x in r.documents_to_request)


def test_every_finding_answers_the_eight_questions():
    bill = prop_bill()
    r = run_audit(bill, POLICY, letter(("Room rent above limit", "6000.00", "3.1"), ("Proportionate deduction", "18000.00", "3.3"),
                                       ("Deduction as per terms", "100.00", None), claimed="56000.00", approved="31900.00"))
    for f in r.findings:
        assert f.what_happened and f.insurer_statement and f.explanation and f.next_step  # 1, 3, analysis, 8
        assert f.insurer_amount is not None  # 2
        assert f.evidence and f.evidence[0].doc_type == "settlement"  # 5
        assert f.conditions and f.classification and f.rule_id
        if f.status == "contestable":
            assert f.contestable_reason and f.policy_clause  # 4, 6
        if f.status == "unverified":
            assert f.missing  # 7
    assert r.findings[0].policy_clause == "Clause 3.1 (Room Rent)"


def test_vague_deduction_classified_by_cited_clause():
    f = one(prop_bill(), ("Deduction as per Clause 3.1", "6000.00", "3.1"))
    assert f.rule_id == "R-ROOM-01" and "taken from the clause it cites" in f.classification


def test_no_legal_conclusions_in_findings():
    r = run_audit(prop_bill(), POLICY, letter(("Proportionate deduction", "18000.00", None)))
    text = " ".join(f.explanation + (f.contestable_reason or "") + f.next_step for f in r.findings).lower()
    for word in ("illegal", "unlawful", "fraud", "guarantee", "entitled to"):
        assert word not in text


# ------------------------------------------------------------------ consistency checks

def checks(report):
    return {c.id: c.status for c in report.checks}


def test_checks_never_pass_without_their_inputs():
    r = run_audit(None, None, letter(("Room rent", "100.00", "3.1")))
    c = checks(r)
    for cid in ("C-REC-01", "C-REC-03", "C-DUP-01", "C-STAY-01", "C-CIT-01", "C-ID-01", "C-OVL-01"):
        assert c[cid] == "not_checked", cid
    assert all(x.detail for x in r.checks)


def test_duplicate_bill_lines_and_deductions():
    bill = HospitalBill(line_items=[item("Doctor visit", 1, "1000.00"), item("Doctor visit", 1, "1000.00")])
    r = run_audit(bill, POLICY, letter(("Non-payable - Masks", "50.00", None), ("Non-payable - Masks", "50.00", None)))
    c = checks(r)
    assert c["C-DUP-01"] == "failed" and c["C-DUP-02"] == "failed"
    dup = next(x for x in r.checks if x.id == "C-DUP-01")
    assert [e.ref for e in dup.evidence] == ["Bill line 1", "Bill line 2"]


def test_deductions_exceeding_the_billed_amount():
    # Gloves billed 300; two deductions take 300 + 200 = 500 from that line
    bill = HospitalBill(line_items=[item("Gloves", 1, "300.00")])
    r = run_audit(bill, POLICY, letter(("Non-payable - Gloves", "300.00", None), ("Gloves not payable", "200.00", None)))
    assert checks(r)["C-OVL-01"] == "failed"
    assert any("Deductions do not exceed what was billed" in m for m in r.missing_information)


def test_length_of_stay_check():
    # admitted 10 Sep, discharged 12 Sep: 2 nights; 4 room days billed > 2 + 1
    bill = HospitalBill(admission_date="10/09/2026", discharge_date="12-Sep-2026",
                        line_items=[item("Room rent", 4, "3000.00")])
    assert checks(run_audit(bill, POLICY, letter()))["C-STAY-01"] == "failed"
    bill3 = bill.model_copy(update={"line_items": [item("Room rent", 3, "3000.00")]})
    assert checks(run_audit(bill3, POLICY, letter()))["C-STAY-01"] == "passed"


def test_identity_and_payment_checks():
    bill = HospitalBill(patient_name="Asha Verma", hospital_name="Sunrise Hospital", line_items=[])
    r = run_audit(bill, POLICY, letter(patient_name="Usha Varma", hospital_name="Sunrise Hospital", policy_number="P/2",
                                       claimed="1000.00", approved="1000.00", paid_amount="900.00"))
    c = checks(r)
    assert (c["C-ID-01"], c["C-ID-02"], c["C-ID-03"], c["C-REC-06"]) == ("failed", "failed", "passed", "failed")


def test_readiness_states():
    bill = prop_bill()
    ok = run_audit(bill, POLICY, letter(("Proportionate deduction", "15000.00", None), claimed="56000.00", approved="41000.00"))
    assert ok.readiness.state == "nothing_to_appeal"
    contest = run_audit(bill, POLICY, letter(("Proportionate deduction", "18000.00", None), claimed="56000.00",
                                             approved="38000.00"))
    assert contest.readiness.state == "ready"
    missing_clause = run_audit(bill, POLICY, letter(("Proportionate deduction", "18000.00", "9.9"), claimed="56000.00",
                                                    approved="38000.00"))
    assert missing_clause.readiness.state == "needs_information"
    assert any("9.9" in x for x in missing_clause.documents_to_request)
