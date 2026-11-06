"""The six SYNTHETIC cases through the full local pipeline: render -> text extraction / OCR -> parser -> audit.
Expected values are hand-computed in synthetic_cases.py; nothing here compares the engine with itself."""

import io
import random
from decimal import Decimal as D

import pytest
from PIL import Image, ImageFilter

from app.demo.fixtures import render_pdf, render_png
from app.services import documents
from app.services.audit import run_audit
from app.services.parsers import is_synthetic, parse_bill, parse_policy, parse_settlement

from .synthetic_cases import BILL_LINES_6, CASES

PARSERS = {"bill": parse_bill, "policy": parse_policy, "settlement": parse_settlement}


def degraded_scan(text: str) -> bytes:
    """A poor scan: half resolution, blurred, with speckle noise. Seeded, so the test is deterministic."""
    img = Image.open(io.BytesIO(render_png(text))).convert("L")
    img = img.resize((img.width // 2, img.height // 2)).filter(ImageFilter.GaussianBlur(0.8))
    rnd, px = random.Random(6), img.load()
    for _ in range(img.width * img.height // 60):
        px[rnd.randrange(img.width), rnd.randrange(img.height)] = rnd.choice((0, 160, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def load(case: dict, scan_bill: bool = False) -> dict:
    """Each document as the API would see it: (parsed document, warnings, text method)."""
    out = {}
    for doc_type, parse in PARSERS.items():
        text = case[doc_type]
        if text is None:
            out[doc_type] = (None, [], None)
            continue
        if doc_type == "bill" and scan_bill:
            raw, method, warn = documents.extract_text("bill.png", degraded_scan(text))
        else:
            raw, method, warn = documents.extract_text(f"{doc_type}.pdf", render_pdf(text))
        assert is_synthetic(raw)  # never mistaken for a real claim
        doc, parse_warn = parse(raw)
        out[doc_type] = (doc, warn + parse_warn, method)
    return out


def audit(docs: dict):
    return run_audit(docs["bill"][0], docs["policy"][0], docs["settlement"][0], demo=True)


@pytest.fixture(scope="module")
def loaded():
    return {name: load(c, scan_bill=name.startswith("6")) for name, c in CASES.items()}


@pytest.mark.parametrize("name", CASES)
def test_extracted_values(loaded, name):
    x, docs = CASES[name]["extracted"], loaded[name]
    bill, policy, letter = (docs[t][0] for t in ("bill", "policy", "settlement"))
    assert letter.claimed_amount == x["claimed"] and letter.approved_amount == x["approved"]
    assert len(letter.deductions) == x["deductions"]
    if name.startswith("6"):
        # Poor scan: the reader may miss or misread values, but it must never pass them off silently.
        assert docs["bill"][2] == "image-ocr"
        truth = [D(a) for _, _, _, a in BILL_LINES_6]
        if [it.amount for it in bill.line_items] != truth or bill.total_amount != x["bill_total"]:
            # Whatever the scan lost or garbled must be visible to the reviewer, not silently trusted.
            assert any("could not be read" in w or "may be misread" in w or "sum to" in w or "missing" in w
                       for w in docs["bill"][1]), docs["bill"][1]
        assert "approved amount not found" in docs["settlement"][1]
        return
    assert docs["bill"][2] == "pdf-text"
    assert len(bill.line_items) == x["lines"] and bill.total_amount == x["bill_total"]
    assert bill.arithmetic_issues() == [] and docs["bill"][1] == []
    assert policy.room_rent_limit_per_day == x["room_limit"]
    if "copay" in x:
        assert policy.copay_percent == x["copay"]


@pytest.mark.parametrize("name", CASES)
def test_audit_matches_hand_calculation(loaded, name):
    e, r = CASES[name]["expected"], audit(loaded[name])
    assert [f.status for f in r.findings] == e["statuses"]
    assert [f.supported_amount for f in r.findings] == e["supported"]
    assert [f.contestable_amount for f in r.findings] == e["contestable"]
    assert [f.basis for f in r.findings] == e["basis"]
    assert (r.total_deductions, r.contestable_total, r.unverified_total, r.supported_total) == (
        e["total"], e["contestable_total"], e["unverified_total"], e["supported_total"])
    for m in e["missing"]:
        assert m in r.missing_information
    if not e["missing"]:
        assert r.missing_information == []
    if "failed_checks" in CASES[name]:
        assert sorted(c.id for c in r.checks if c.status == "failed") == sorted(CASES[name]["failed_checks"])


@pytest.mark.parametrize("name", CASES)
def test_no_false_certainty(loaded, name):
    docs = loaded[name]
    r = audit(docs)
    assert r.supported_total + r.contestable_total + r.unverified_total == r.total_deductions
    for f in r.findings:
        assert f.evidence[0].doc_type == "settlement" and f.basis_label
        if f.status == "contestable":  # a contestable amount must rest on a calculation or on policy wording
            assert f.calculation or any(e.doc_type == "policy" for e in f.evidence) or f.basis == "clause_absent"
        if f.status == "unverified":
            assert f.supported_amount is None and f.contestable_amount == 0
    if docs["policy"][0] is None:
        assert all(f.status == "unverified" for f in r.findings) and r.contestable_total == 0


def test_case6_still_safe_when_policy_is_added(loaded):
    """Even with a policy, a bill without readable room days must not produce a contestable room-rent figure."""
    docs = loaded["6_incomplete_poor_quality"]
    policy, _ = parse_policy(CASES["5_absent_clause"]["policy"])
    bill = docs["bill"][0]
    r = run_audit(bill, policy, docs["settlement"][0])
    room = r.findings[0]
    if any(it.category == "room_rent" and it.quantity for it in bill.line_items):
        assert room.status in ("supported", "contestable") and room.calculation  # recalculated from the bill
    else:
        assert room.status == "unverified"


# ------------------------------------------------------------------ missing and conflicting evidence


def test_case2_without_bill_cannot_recalculate(loaded):
    docs = loaded["2_room_rent_proportionate"]
    r = run_audit(None, docs["policy"][0], docs["settlement"][0])
    assert [f.status for f in r.findings] == ["unverified", "unverified"] and r.contestable_total == 0
    assert any("Hospital bill not provided" in m for m in r.missing_information)


def test_case2_conflicting_clause_citation_is_flagged(loaded):
    docs = loaded["2_room_rent_proportionate"]
    letter = docs["settlement"][0]
    wrong = letter.model_copy(update={"deductions": [
        letter.deductions[0].model_copy(update={"clause_ref": "3.3"}), letter.deductions[1]]})
    f = run_audit(docs["bill"][0], docs["policy"][0], wrong).findings[0]
    assert f.status == "supported" and "cites Clause 3.3" in f.explanation and "Clause 3.1" in f.explanation


def test_case1_conflicting_totals_are_reported(loaded):
    docs = loaded["1_straightforward"]
    letter = docs["settlement"][0].model_copy(update={"total_deductions": D("250.00"), "approved_amount": D("14850.75")})
    r = run_audit(docs["bill"][0], docs["policy"][0], letter)
    gap = r.findings[-1]
    assert (gap.category, gap.status, gap.insurer_amount, gap.basis) == (
        "Unexplained difference", "unverified", 100, "reconciliation")
    assert any("states total deductions Rs 250.00" in m for m in r.missing_information)


def test_case3_conditional_copay_stays_unverified(loaded):
    docs = loaded["3_copay_sublimit"]
    policy, _ = parse_policy(CASES["3_copay_sublimit"]["policy"].replace(
        "applies to every admissible claim.", "applies to every admissible claim where the Insured Person is aged "
                                              "61 years or above."))
    f = run_audit(docs["bill"][0], policy, docs["settlement"][0]).findings[1]
    assert f.status == "unverified" and "aged 61" in f.explanation and "8,800.00" in f.explanation


def test_case4_list_by_reference_is_not_contested(loaded):
    """If the non-payable clause points to an annexure that was not uploaded, unlisted items are unverified."""
    docs = loaded["4_non_payable"]
    policy, _ = parse_policy(CASES["4_non_payable"]["policy"].replace(
        "not payable under this policy:", "not payable under this policy, together with the items in Annexure I:"))
    f = run_audit(docs["bill"][0], policy, docs["settlement"][0]).findings[2]
    assert f.status == "unverified" and "Annexure I" in f.explanation


def test_case5_missing_clause_without_citation_is_contestable(loaded):
    """Control for case 5: when the insurer cites no clause, an unlisted item is contestable on the policy as given."""
    docs = loaded["5_absent_clause"]
    letter = docs["settlement"][0]
    plain = letter.model_copy(update={"deductions": [letter.deductions[0].model_copy(update={"clause_ref": None})]})
    f = run_audit(docs["bill"][0], docs["policy"][0], plain).findings[0]
    assert (f.status, f.contestable_amount, f.basis) == ("contestable", 1200, "clause_absent")


def test_vague_deduction_is_classified_by_its_cited_clause(loaded):
    docs = loaded["4_non_payable"]
    letter = docs["settlement"][0]
    vague = letter.model_copy(update={"deductions": [letter.deductions[2].model_copy(
        update={"description": "Deduction as per Clause 7.1 - Nebulizer kit"})]})
    f = run_audit(docs["bill"][0], docs["policy"][0], vague).findings[0]
    assert f.category == "Non-payable items" and f.status == "contestable"
    assert "taken from the clause it cites" in f.calculation[0]


def test_integer_bill_amounts_are_read_only_when_arithmetic_proves_them():
    bill, warnings = parse_bill("Room rent 3 x 4500 = 13500\nSurgeon fee 1 x 30000 = 30000\n"
                                "Misprint 2 x 100 = 250\nGrand Total 43500")
    assert [it.amount for it in bill.line_items] == [13500, 30000] and bill.total_amount == 43500
    assert any("Misprint" in w for w in warnings)


def test_single_amount_column_is_not_split_into_rate_and_amount():
    """Regression: "Pharmacy 4,800.00" used to parse as rate 4,80 and amount 0.00."""
    bill, warnings = parse_bill("Pharmacy 4,800.00\nSurgeon fee 20,000.00\nTotal 24,800.00")
    assert [(it.unit_price, it.amount) for it in bill.line_items] == [(None, 4800), (None, 20000)]
    assert warnings == []
