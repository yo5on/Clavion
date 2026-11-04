"""SYNTHETIC demo case: a hospital bill, policy wording and settlement letter with known expected audit results.
All names, numbers and organisations are invented. Every document carries the SYNTHETIC marker and FIXTURE_ID,
and everything derived from them is labelled demo in the UI and in exported PDFs."""

import io
import re
from decimal import Decimal

from ..schemas.bill import BillLineItem, HospitalBill
from ..schemas.claim import PolicyDocument, SettlementDeduction, SettlementLetter, SubLimit
from ..services.parsers import split_clauses

FIXTURE_ID = "CLAVION-DEMO-001"
D = Decimal

# (description, qty, rate, amount, category)
BILL_ITEMS = [
    ("Room rent - Private room", 4, "6500.00", "26000.00", "room_rent"),
    ("ICU charges", 1, "12000.00", "12000.00", "icu"),
    ("Surgeon fee - Laparoscopic appendectomy", 1, "45000.00", "45000.00", "professional"),
    ("Anaesthetist fee", 1, "12000.00", "12000.00", "professional"),
    ("Operation theatre charges", 1, "18500.00", "18500.00", "ot"),
    ("Pharmacy and medical consumables", 1, "9840.50", "9840.50", "pharmacy"),
    ("Laboratory investigations", 6, "850.00", "5100.00", "diagnostics"),
    ("Gloves, masks and PPE kit", 4, "375.00", "1500.00", "consumables"),
    ("Registration and admission charges", 1, "1000.00", "1000.00", "admin"),
]
BILL_TOTAL = D("130940.50")

BILL_TEXT = "\n".join([
    "*** SYNTHETIC TEST DOCUMENT - NOT A REAL BILL ***",
    f"Ref: {FIXTURE_ID}",
    "Sunrise Multispeciality Hospital",
    "FINAL IN-PATIENT BILL",
    "Bill No: SMH/IP/2026/004521    Bill Date: 12-Oct-2026",
    "Patient Name: Asha Verma",
    "",
    "    Description                                Qty   Rate (Rs)     Amount (Rs)",
    *(f"{i:>2}. {d:<42} {q:>3} x {D(r):>10,.2f} = {D(a):>11,.2f}" for i, (d, q, r, a, _) in enumerate(BILL_ITEMS, 1)),
    "",
    f"    GRAND TOTAL (Rs)                                           {BILL_TOTAL:>11,.2f}",
])

POLICY_TEXT = f"""*** SYNTHETIC TEST DOCUMENT - NOT A REAL POLICY ***
Suraksha Health Plus - Policy Wording
Ref: {FIXTURE_ID}
Policy No: SHP/2026/55501
Insured: Asha Verma
Sum Insured: Rs 5,00,000

1. Scope of Cover
The Company will indemnify reasonable and customary medical expenses incurred on
hospitalisation for at least 24 hours, subject to the limits below.

4.1 Room Rent
Room rent, boarding and nursing expenses are payable up to 1% of the Sum Insured
per day, subject to a maximum of Rs 5,000 per day.

4.2 Intensive Care Unit
ICU charges are payable up to 2% of the Sum Insured per day, subject to a
maximum of Rs 10,000 per day.

4.3 Proportionate Deduction
If the Insured Person occupies a room category with rent higher than the
eligible room rent, the associated medical expenses shall be payable in the same
proportion as the eligible room rent bears to the actual room rent.
Proportionate deduction shall not apply to pharmacy, consumables, implants,
medical devices and diagnostics.

4.4 Sub-limits
The following sub-limits apply per policy year:
- Cataract surgery: Rs 40,000 per eye
- Knee replacement: Rs 1,50,000 per knee

5.1 Co-payment
A co-payment of 10% applies to every admissible claim where the Insured Person
is aged 61 years or above at the time of admission.

7.2 Non-payable Items
The following items are not payable under this policy:
- Gloves
- Masks
- PPE kit
- Attendant charges
- Food charges for attendant
"""

SETTLEMENT_TEXT = f"""*** SYNTHETIC TEST DOCUMENT - NOT A REAL SETTLEMENT LETTER ***
Bharat Shield General Insurance Ltd
Ref: {FIXTURE_ID}
CLAIM SETTLEMENT LETTER
Letter Date: 28-Oct-2026
Claim No: CLM/2026/778812
Policy No: SHP/2026/55501
Patient Name: Asha Verma
Hospital: Sunrise Multispeciality Hospital

Amount Claimed: Rs 1,30,940.50

Deductions:
1. Room rent in excess of eligible limit (Clause 4.1)  Rs 6,000.00
2. Proportionate deduction on associated charges (Clause 4.3)  Rs 20,870.88
3. ICU charges in excess of eligible limit (Clause 4.2)  Rs 2,000.00
4. Non-payable items - Gloves, masks and PPE kit (Clause 7.2)  Rs 1,500.00
5. Non-payable items - Registration and admission charges (Clause 7.2)  Rs 1,000.00
6. Deduction as per policy terms and conditions  Rs 2,500.00

Total Deductions: Rs 33,870.88
Amount Approved: Rs 97,069.62
"""

TEXTS = {"bill": BILL_TEXT, "policy": POLICY_TEXT, "settlement": SETTLEMENT_TEXT}

# Expected audit results, worked by hand:
#  1 room rent (6500 - 5000) x 4 = 6,000.00                                        supported
#  2 proportionate on surgeon + anaesthetist + OT = 75,500 x (1 - 5000/6500) = 17,423.08;
#    insurer applied it to 90,440.50 (also pharmacy and lab) = 20,870.88        -> 3,447.80 contestable
#  3 ICU (12000 - 10000) x 1 = 2,000.00                                            supported
#  4 gloves, masks, PPE kit are listed in clause 7.2 = 1,500.00                    supported
#  5 registration charges are not listed in clause 7.2                          -> 1,000.00 contestable
#  6 no reason or clause given                                                  -> 2,500.00 unverified
EXPECTED = {
    "statuses": ["supported", "contestable", "supported", "supported", "contestable", "unverified"],
    "supported_amounts": [D("6000.00"), D("17423.08"), D("2000.00"), D("1500.00"), D("0.00"), None],
    "contestable_amounts": [D("0.00"), D("3447.80"), D("0.00"), D("0.00"), D("1000.00"), D("0.00")],
    "total_deductions": D("33870.88"),
    "contestable_total": D("4447.80"),
    "unverified_total": D("2500.00"),
    "supported_total": D("26923.08"),
}


def ground_truth(doc_type: str):
    if doc_type == "bill":
        return HospitalBill(hospital_name="Sunrise Multispeciality Hospital", bill_number="SMH/IP/2026/004521",
                            patient_name="Asha Verma", bill_date="12-Oct-2026", total_amount=BILL_TOTAL,
                            line_items=[BillLineItem(description=d, quantity=q, unit_price=r, amount=a, category=c)
                                        for d, q, r, a, c in BILL_ITEMS])
    if doc_type == "policy":
        return PolicyDocument(
            policy_name="Suraksha Health Plus - Policy Wording", policy_number="SHP/2026/55501",
            sum_insured=D("500000"), room_rent_limit_per_day=D("5000"), room_rent_clause="4.1",
            icu_limit_per_day=D("10000"), icu_clause="4.2", proportionate_clause="4.3",
            proportionate_exclusions=["consumables", "diagnostics", "implants", "pharmacy"],
            copay_percent=D("10"), copay_clause="5.1",
            copay_condition="where the Insured Person is aged 61 years or above at the time of admission",
            non_payable_items=["Gloves", "Masks", "PPE kit", "Attendant charges", "Food charges for attendant"],
            non_payable_clause="7.2",
            sub_limits=[SubLimit(name="Cataract surgery", limit="40000", clause_id="4.4"),
                        SubLimit(name="Knee replacement", limit="150000", clause_id="4.4")],
            clauses=split_clauses(POLICY_TEXT))  # clause text is verbatim; splitting it is purely mechanical
    if doc_type == "settlement":
        ded = [("Room rent in excess of eligible limit (Clause 4.1)", "6000.00", "4.1"),
               ("Proportionate deduction on associated charges (Clause 4.3)", "20870.88", "4.3"),
               ("ICU charges in excess of eligible limit (Clause 4.2)", "2000.00", "4.2"),
               ("Non-payable items - Gloves, masks and PPE kit (Clause 7.2)", "1500.00", "7.2"),
               ("Non-payable items - Registration and admission charges (Clause 7.2)", "1000.00", "7.2"),
               ("Deduction as per policy terms and conditions", "2500.00", None)]
        return SettlementLetter(
            insurer_name="Bharat Shield General Insurance Ltd", claim_number="CLM/2026/778812",
            policy_number="SHP/2026/55501", patient_name="Asha Verma",
            hospital_name="Sunrise Multispeciality Hospital", claimed_amount="130940.50",
            approved_amount="97069.62", total_deductions="33870.88",
            deductions=[SettlementDeduction(description=d, amount=a, clause_ref=c) for d, a, c in ded])
    raise ValueError(doc_type)


def render_pdf(text: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=8)
    for line in text.splitlines():
        pdf.cell(0, 4.2, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def render_png(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    lines = text.splitlines()
    font = ImageFont.load_default(size=22)
    img = Image.new("RGB", (1500, 60 + 40 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        for seg in re.finditer(r"\S+(?: \S+)*", line):  # runs split by 2+ spaces become separate columns, as on a scan
            d.text((30 + 12 * seg.start(), 30 + 40 * i), seg.group(), fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
