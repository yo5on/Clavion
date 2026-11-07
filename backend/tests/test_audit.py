"""Audit engine on SYNTHETIC claims with hand-computed expected results."""

from decimal import Decimal as D

from app.demo import fixtures
from app.schemas.bill import HospitalBill
from app.schemas.claim import PolicyDocument, SettlementLetter
from app.services import calculations as calc
from app.services.audit import classify_deduction, run_audit
from app.services.parsers import parse_policy
from app.services.policy_analysis import search_clauses

BILL, POLICY, LETTER = (fixtures.ground_truth(t) for t in ("bill", "policy", "settlement"))


def test_demo_case_matches_expected_results():
    r = run_audit(BILL, POLICY, LETTER, demo=True)
    e = fixtures.EXPECTED
    assert [f.status for f in r.findings] == e["statuses"]
    assert [f.supported_amount for f in r.findings] == e["supported_amounts"]
    assert [f.contestable_amount for f in r.findings] == e["contestable_amounts"]
    assert (r.total_deductions, r.contestable_total, r.unverified_total, r.supported_total) == (
        e["total_deductions"], e["contestable_total"], e["unverified_total"], e["supported_total"])
    assert r.supported_total + r.contestable_total + r.unverified_total == r.total_deductions
    assert r.bill_total == fixtures.BILL_TOTAL and r.demo and "no AI" in r.method
    assert r.missing_information == []


def test_findings_cite_evidence_that_exists():
    r = run_audit(BILL, POLICY, LETTER)
    ids = {c.id for c in POLICY.clauses}
    for f in r.findings:
        assert f.evidence[0].doc_type == "settlement"
        for ev in f.evidence:
            if ev.doc_type == "policy" and ev.found:
                assert ev.ref.removeprefix("Clause ") in ids and ev.excerpt == POLICY.clause(ev.ref[7:]).text
            if ev.doc_type == "bill":
                n = int(ev.ref.removeprefix("Bill line "))
                assert BILL.line_items[n - 1].description in ev.excerpt
    prop = r.findings[1]
    assert "Clause 4.3" in [e.ref for e in prop.evidence] and prop.related_clauses[0] == "4.3"
    assert any("75,500.00" in step for step in prop.calculation)


def test_classify_deductions():
    assert [classify_deduction(d.description) for d in LETTER.deductions] == [
        "room_rent_excess", "proportionate", "icu_excess", "non_payable", "non_payable", "unspecified"]


def test_missing_policy_marks_everything_unverified():
    r = run_audit(BILL, None, LETTER)
    assert {f.status for f in r.findings} == {"unverified"} and r.contestable_total == 0
    assert any("Policy not provided" in m for m in r.missing_information)


def test_missing_settlement_has_no_findings():
    r = run_audit(BILL, POLICY, None)
    assert r.findings == [] and any("Settlement letter not provided" in m for m in r.missing_information)


def test_unexplained_reduction_and_missing_cited_clause():
    letter = LETTER.model_copy(update={"approved_amount": D("96069.62"), "deductions": [
        LETTER.deductions[0].model_copy(update={"clause_ref": "9.9"})]})
    r = run_audit(BILL, POLICY, letter)
    gap = r.findings[-1]
    assert gap.category == "Unexplained difference" and gap.status == "unverified"
    assert gap.insurer_amount == D("130940.50") - D("96069.62") - D("6000.00")
    assert any(e.ref == "Clause 9.9" and not e.found for e in r.findings[0].evidence)
    assert any("Clause 9.9" in m for m in r.missing_information)


def test_sublimit_and_copay_scenario():
    policy, _ = parse_policy("""Sum Insured: Rs 3,00,000
4.4 Sub-limits
- Cataract surgery: Rs 40,000 per eye
5.1 Co-payment
A co-payment of 10% applies to every admissible claim.""")
    bill = HospitalBill(line_items=[{"description": "Cataract surgery package (right eye)", "amount": "65000.00"}])
    letter = SettlementLetter(claimed_amount="65000.00", approved_amount="31500.00", deductions=[
        {"description": "Amount above cataract sub-limit", "amount": "30000.00"},
        {"description": "Co-payment 10%", "amount": "3500.00"}])
    sub, copay = run_audit(bill, policy, letter).findings
    assert (sub.status, sub.supported_amount, sub.contestable_amount) == ("contestable", D("25000.00"), D("5000.00"))
    # The insurer's 5,000 sub-limit over-deduction must not shrink the co-pay base: CLAVION uses its own 25,000.
    # admissible = 65,000 - 25,000 = 40,000; 10% = 4,000. Insurer took 3,500 (less), so nothing to contest.
    assert (copay.status, copay.supported_amount, copay.contestable_amount) == ("supported", D("4000.00"), D("0.00"))


def test_conditional_copay_is_unverified():
    r = run_audit(BILL, POLICY, SettlementLetter(claimed_amount="1000.00", approved_amount="900.00",
                                                 deductions=[{"description": "Co-payment", "amount": "100.00"}]))
    assert r.findings[0].status == "unverified" and "aged 61" in r.findings[0].explanation


def test_no_proportionate_clause_makes_deduction_contestable():
    policy = POLICY.model_copy(update={"proportionate_clause": None})
    f = run_audit(BILL, policy, LETTER).findings[1]
    assert (f.status, f.contestable_amount) == ("contestable", D("20870.88"))


def test_clause_search_ranks_relevant_clause_first():
    assert search_clauses(POLICY.clauses, "gloves masks non-payable")[0][0].id == "7.2"
    assert search_clauses(POLICY.clauses, "intensive care unit charges")[0][0].id == "4.2"
    assert search_clauses(PolicyDocument().clauses, "anything") == []


def test_money_helpers():
    assert calc.excess_over_daily_limit("6500", "5000", 4) == D("6000.00")
    assert calc.excess_over_daily_limit("4000", "5000", 4) == D("0.00")
    assert calc.sublimit_deduction("65000", "40000") == D("25000.00")
    assert calc.copay_amount("35000", "10") == D("3500.00")
    assert calc.contestable("100", "150") == D("0.00")
    assert calc.reconciliation_gap("130940.50", "97069.62", ["33870.88"]) == D("0.00")
    assert calc.bill_total(["0.10", "0.20"]) == D("0.30")  # Decimal, not float
