"""SYNTHETIC hospital bill used only for API capability tests. All names and numbers are invented."""

from decimal import Decimal
from pathlib import Path

HOSPITAL = "Sunrise Multispeciality Hospital"
BILL_NUMBER = "SMH/IP/2026/004521"
PATIENT = "Asha Verma"
BILL_DATE = "12-Oct-2026"
# (description, quantity, unit price, amount)
ITEMS = [
    ("Room rent - Private room", 4, "6500.00", "26000.00"),
    ("ICU charges", 1, "12000.00", "12000.00"),
    ("Surgeon fee - Laparoscopic appendectomy", 1, "45000.00", "45000.00"),
    ("Anaesthetist fee", 1, "12000.00", "12000.00"),
    ("Operation theatre charges", 1, "18500.00", "18500.00"),
    ("Pharmacy and medical consumables", 1, "9840.50", "9840.50"),
    ("Laboratory investigations", 6, "850.00", "5100.00"),
    ("Gloves, masks and PPE kit", 4, "375.00", "1500.00"),
    ("Registration and admission charges", 1, "1000.00", "1000.00"),
]
TOTAL = sum(Decimal(a) for *_, a in ITEMS)
assert TOTAL == Decimal("130940.50")


def as_text() -> str:
    rows = "\n".join(f"{i:>2}. {d:<42} {q:>3} x {Decimal(u):>10,.2f} = {Decimal(a):>11,.2f}"
                     for i, (d, q, u, a) in enumerate(ITEMS, 1))
    return (f"*** SYNTHETIC TEST DOCUMENT - NOT A REAL BILL ***\n{HOSPITAL}\nFINAL IN-PATIENT BILL\n"
            f"Bill No: {BILL_NUMBER}    Bill Date: {BILL_DATE}\nPatient: {PATIENT}\n\n"
            f"    Description                                Qty   Rate (Rs)     Amount (Rs)\n{rows}\n\n"
            f"    GRAND TOTAL (Rs)                                           {TOTAL:>11,.2f}\n")


def render_png(path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = lambda s: ImageFont.load_default(size=s)  # noqa: E731
    img = Image.new("RGB", (1100, 760), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 20), "SYNTHETIC TEST DOCUMENT - NOT A REAL BILL", fill=(200, 0, 0), font=font(18))
    d.text((40, 55), HOSPITAL, fill="black", font=font(30))
    d.text((40, 95), "FINAL IN-PATIENT BILL", fill="black", font=font(20))
    d.text((40, 135), f"Bill No: {BILL_NUMBER}", fill="black", font=font(18))
    d.text((620, 135), f"Bill Date: {BILL_DATE}", fill="black", font=font(18))
    d.text((40, 165), f"Patient Name: {PATIENT}", fill="black", font=font(18))
    cols = [40, 90, 620, 720, 900]
    y = 215
    for x, h in zip(cols, ["#", "Description", "Qty", "Rate (Rs)", "Amount (Rs)"]):
        d.text((x, y), h, fill="black", font=font(18))
    d.line((40, y + 28, 1060, y + 28), fill="black", width=2)
    for i, (desc, q, u, a) in enumerate(ITEMS, 1):
        y += 40
        for x, v in zip(cols, [str(i), desc, str(q), f"{Decimal(u):,.2f}", f"{Decimal(a):,.2f}"]):
            d.text((x, y), v, fill="black", font=font(17))
    y += 45
    d.line((40, y, 1060, y), fill="black", width=2)
    d.text((620, y + 15), "GRAND TOTAL", fill="black", font=font(20))
    d.text((900, y + 15), f"{TOTAL:,.2f}", fill="black", font=font(20))
    img.save(path)
    return path


def compare(bill) -> list[str]:
    """Differences between an extracted HospitalBill and the ground truth above."""
    diffs = []
    for field, want in [("hospital_name", HOSPITAL), ("bill_number", BILL_NUMBER), ("patient_name", PATIENT)]:
        got = getattr(bill, field) or ""
        if want.lower() not in got.lower():
            diffs.append(f"{field}: got {got!r}, want {want!r}")
    if "12" not in (bill.bill_date or "") or "2026" not in (bill.bill_date or ""):
        diffs.append(f"bill_date: got {bill.bill_date!r}, want {BILL_DATE!r}")
    if len(bill.line_items) != len(ITEMS):
        diffs.append(f"line_items: got {len(bill.line_items)}, want {len(ITEMS)}")
    for (desc, q, _, a), it in zip(ITEMS, bill.line_items):
        if it.amount != Decimal(a) or (it.quantity is not None and it.quantity != q):
            diffs.append(f"'{desc}': got qty={it.quantity} amount={it.amount}, want qty={q} amount={a}")
    if bill.total_amount != TOTAL:
        diffs.append(f"total_amount: got {bill.total_amount}, want {TOTAL}")
    return diffs
