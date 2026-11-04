"""Local deterministic parsers: plain text -> validated Pydantic documents. No model is involved.

They target the layouts Indian hospital bills, policy wordings and settlement letters commonly use (labelled
header fields, one line item per line, numbered clauses). Anything they miss is left null and flagged, and the
user corrects it on the review screen.
"""

import re
from decimal import Decimal

from ..schemas.bill import BillLineItem, HospitalBill
from ..schemas.claim import PolicyClause, PolicyDocument, SettlementDeduction, SettlementLetter, SubLimit

# shortcut: plain integers without a comma or decimals (e.g. "26000") are not read as money, so bills printed
# that way lose their line items; upgrade by scoring numeric columns per document if real bills need it.
MONEY = r"(?:\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{1,2})"
RS = r"(?:Rs\.?|INR|₹)"
RS_AMOUNT = rf"{RS}\s*({MONEY}|\d+)"
SYNTHETIC_MARKER = "SYNTHETIC TEST DOCUMENT"

# Order matters: the first matching category wins.
CATEGORIES: list[tuple[str, str]] = [
    ("icu", r"\bicu\b|\biccu\b|\bnicu\b|intensive\s*care"),
    ("room_rent", r"room\s*(?:rent|charges?)|bed\s*charges?|\bward\b|boarding"),
    ("pharmacy", r"pharmacy|medicine|drugs?\b"),
    ("consumables", r"consumable|gloves?|masks?|\bppe\b|syringe|disposable"),
    ("implants", r"implant|stent|\blens\b|prosthe"),
    ("diagnostics", r"\blab\b|laborator|investigation|x-?ray|\bscan\b|\bmri\b|\bct\b|patholog|radiolog|diagnostic"),
    ("ot", r"operation\s*theat|\bot\b"),
    ("professional", r"surgeon|anaesth|anesth|doctor|consult|physician|visit"),
    ("nursing", r"nursing"),
    ("admin", r"registration|admission|admin|documentation|file\s*charge"),
]
CATEGORY_LABELS = {"icu": "ICU", "room_rent": "Room rent", "pharmacy": "Pharmacy", "consumables": "Consumables",
                   "implants": "Implants & devices", "diagnostics": "Diagnostics", "ot": "Operation theatre",
                   "professional": "Professional fees", "nursing": "Nursing", "admin": "Administrative",
                   "other": "Other"}
# Words a policy uses when it lists categories the proportionate deduction does not apply to.
EXCLUSION_WORDS = {"pharmacy": "pharmacy", "medicine": "pharmacy", "drug": "pharmacy", "consumable": "consumables",
                   "implant": "implants", "device": "implants", "diagnostic": "diagnostics",
                   "investigation": "diagnostics", "icu": "icu"}


def money(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def categorize(description: str) -> str:
    d = description.lower()
    return next((cat for cat, pat in CATEGORIES if re.search(pat, d)), "other")


def _search(pattern: str, text: str, flags=re.I | re.M) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _amount_after(label: str, text: str) -> Decimal | None:
    v = _search(rf"{label}\s*[:\-]?\s*{RS}?\s*({MONEY}|\d+)", text)
    return money(v) if v else None


def _lines(text: str) -> list[str]:
    return [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]


# ---------------------------------------------------------------- hospital bill

ITEM_RE = re.compile(
    rf"^(?:\d{{1,3}}(?:[.)]\s*|\s+)(?=[A-Za-z]))?(?P<desc>.*?[A-Za-z].*?)\s+"
    rf"(?:(?P<qty>\d+(?:\.\d+)?)\s*(?:[xX×*]\s*|\s+))?(?:(?P<rate>{MONEY})\s*=?\s*)?(?P<amt>{MONEY})$")
TOTAL_RE = re.compile(r"grand\s*total|net\s*(?:amount|payable)|total\s*(?:amount|bill)|bill\s*total|^total\b", re.I)
SKIP_RE = re.compile(r"sub\s*-?\s*total|discount|advance|deposit|paid|balance|tax|gst", re.I)


def parse_bill(text: str) -> tuple[HospitalBill, list[str]]:
    lines = _lines(text)
    items, total = [], None
    for ln in lines:
        if TOTAL_RE.search(ln):
            if total is None and (amts := re.findall(MONEY, ln)):
                total = money(amts[-1])
            continue
        if SKIP_RE.search(ln) or not (m := ITEM_RE.match(ln)):
            continue
        amount = money(m["amt"])
        rate = money(m["rate"]) if m["rate"] else None
        qty = Decimal(m["qty"]) if m["qty"] else None
        if qty is None and rate:  # OCR often misses short qty values; infer when it is a whole number
            q = amount / rate
            qty = q if q == q.to_integral_value() and q > 0 else None
        desc = m["desc"].strip(" -:.")
        items.append(BillLineItem(description=desc, quantity=qty, unit_price=rate, amount=amount,
                                  category=categorize(desc)))
    bill = HospitalBill(
        hospital_name=next((ln for ln in lines if re.search(r"hospital|medical|clinic|nursing home|institute",
                                                            ln, re.I) and not re.search(r"bill|:", ln, re.I)), None),
        bill_number=_search(r"Bill\s*No\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*?)(?=\s|$|Bill|Date)", text),
        patient_name=_search(r"Patient(?:\s*Name)?\s*[:\-]\s*([A-Za-z][A-Za-z .']*?)(?:\s{2,}|\s*$)", text),
        bill_date=_search(r"Bill\s*Date\s*[:\-]?\s*(\d{1,2}[-/ ][A-Za-z0-9]{2,9}[-/ ]\d{2,4})", text),
        line_items=items,
        total_amount=total,
    )
    warnings = bill.arithmetic_issues()
    if not items:
        warnings.append("no line items recognised; add them on the review screen")
    return bill, warnings


# ---------------------------------------------------------------- settlement letter

DEDUCTION_RE = re.compile(rf"^(?:\d{{1,3}}[.)]\s*)?(?P<desc>.*?[A-Za-z].*?)\s*[:\-]?\s*{RS}?\s*(?P<amt>{MONEY})$")


def parse_settlement(text: str) -> tuple[SettlementLetter, list[str]]:
    lines = _lines(text)
    deductions: list[SettlementDeduction] = []
    in_section = False
    for ln in lines:
        if re.match(r"^(?:details\s+of\s+)?deductions?\b[^0-9]*$", ln, re.I):
            in_section = True
            continue
        if in_section and re.search(r"total\s*deduct|amount\s*(?:approved|settled|payable)|approved\s*amount", ln, re.I):
            break
        if in_section and (m := DEDUCTION_RE.match(ln)):
            desc = m["desc"].strip(" -:.")
            deductions.append(SettlementDeduction(
                description=desc, amount=money(m["amt"]),
                clause_ref=_search(r"(?:Clause|Section)\s*(\d+(?:\.\d+)*)", desc)))
    letter = SettlementLetter(
        insurer_name=next((ln for ln in lines if re.search(r"insurance|assurance", ln, re.I)
                           and SYNTHETIC_MARKER not in ln), None),
        claim_number=_search(r"Claim\s*(?:No|Number|ID)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)", text),
        policy_number=_search(r"Policy\s*(?:No|Number)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)", text),
        patient_name=_search(r"Patient(?:\s*Name)?\s*[:\-]\s*([A-Za-z][A-Za-z .']*?)(?:\s{2,}|\s*$)", text),
        hospital_name=_search(r"Hospital(?:\s*Name)?\s*[:\-]\s*(.+?)(?:\s{2,}|\s*$)", text),
        claimed_amount=_amount_after(r"(?:Amount\s*Claimed|Claimed\s*Amount|Claim\s*Amount)", text),
        approved_amount=_amount_after(r"(?:Amount\s*(?:Approved|Settled|Payable)|(?:Approved|Settled)\s*Amount)", text),
        total_deductions=_amount_after(r"Total\s*Deductions?", text),
        deductions=deductions,
    )
    warnings = []
    if not deductions:
        warnings.append("no itemised deductions recognised; add them on the review screen")
    for field in ("claimed_amount", "approved_amount"):
        if getattr(letter, field) is None:
            warnings.append(f"{field.replace('_', ' ')} not found")
    return letter, warnings


# ---------------------------------------------------------------- policy wording

CLAUSE_RE = re.compile(r"^(?:(?:Clause|Section)\s+)?(\d{1,2}(?:\.\d{1,2})*)[.)]?\s+([A-Z(].*)$")
ANNEX_RE = re.compile(r"^((?:Annexure|Schedule|Appendix)\s*[\w-]*)\s*[:\-]?\s*(.*)$", re.I)


def split_clauses(text: str) -> list[PolicyClause]:
    clauses: list[PolicyClause] = []
    cur_id, cur_title, buf = "preamble", "Preamble", []

    def flush():
        if buf:
            clauses.append(PolicyClause(id=cur_id, title=cur_title, text="\n".join(buf)))

    for ln in _lines(text):
        m = CLAUSE_RE.match(ln) or ANNEX_RE.match(ln)
        if m:
            flush()
            cur_id, rest = m.group(1), m.group(2)
            cur_title = re.split(r"[:.]\s", rest, maxsplit=1)[0][:80] or cur_id
            buf = [ln]
        else:
            buf.append(ln)
    flush()
    return clauses


def _find_clause(clauses, title_pat: str, text_pat: str | None = None, exclude: str | None = None):
    for field in ("title", "text"):
        for c in clauses:
            hay = c.title if field == "title" else c.text
            if re.search(title_pat, hay, re.I) and (not exclude or not re.search(exclude, c.title, re.I)) \
                    and (not text_pat or re.search(text_pat, c.text, re.I)):
                return c
    return None


def _per_day_limit(c: PolicyClause | None, sum_insured: Decimal | None) -> Decimal | None:
    """Limit per day = the smaller of an explicit 'Rs X per day' and 'Y% of Sum Insured', when both are given."""
    if not c:
        return None
    candidates = [money(v) for v in re.findall(rf"{RS_AMOUNT}\s*(?:per|a|/)\s*day", c.text, re.I)]
    if sum_insured and (pct := _search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(?:the\s*)?sum\s*insured", c.text)):
        candidates.append((Decimal(pct) / 100 * sum_insured).quantize(Decimal("0.01")))
    return min(candidates) if candidates else None


def _bullets(c: PolicyClause) -> list[str]:
    return [re.sub(r"^[-•*–]\s*", "", ln).strip() for ln in c.text.splitlines()[1:] if re.match(r"^[-•*–]", ln)]


def parse_policy(text: str) -> tuple[PolicyDocument, list[str]]:
    clauses = split_clauses(text)
    si = _amount_after(r"Sum\s+Insured", text)
    room = _find_clause(clauses, r"room\s*rent", r"per\s*day", exclude=r"icu|intensive|proportion")
    icu = _find_clause(clauses, r"\bicu\b|intensive\s*care", r"per\s*day")
    prop = _find_clause(clauses, r"proportion")
    copay = _find_clause(clauses, r"co-?\s*pay")
    nonpay = _find_clause(clauses, r"non[- ]?payable|not\s+payable")
    subl = _find_clause(clauses, r"sub[- ]?limit")

    exclusions: list[str] = []
    if prop and (m := re.search(r"not\s+apply\s+to\s+([^.]+)", prop.text, re.I)):
        exclusions = sorted({cat for word, cat in EXCLUSION_WORDS.items() if word in m.group(1).lower()})

    sub_limits = []
    if subl:
        for b in _bullets(subl):
            if m := re.match(rf"(.+?)\s*[:\-–]\s*(?:up\s*to\s*)?{RS_AMOUNT}", b, re.I):
                sub_limits.append(SubLimit(name=m.group(1).strip(), limit=money(m.group(2)), clause_id=subl.id))

    non_payable = []
    if nonpay:
        non_payable = _bullets(nonpay) or [s.strip() for s in re.split(r",|;|\band\b", nonpay.text.split(":", 1)[-1])
                                           if 2 < len(s.strip()) < 60]

    copay_pct = _search(r"co-?\s*payment\s+of\s+(\d+(?:\.\d+)?)\s*%", copay.text) if copay else None
    copay_cond = _search(r"((?:where|if|for)\s[^.]+)", " ".join(copay.text.split("\n")[1:])) if copay_pct else None

    doc = PolicyDocument(
        policy_name=next((ln for ln in _lines(text) if SYNTHETIC_MARKER not in ln), None),
        policy_number=_search(r"Policy\s*(?:No|Number)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)", text),
        sum_insured=si,
        room_rent_limit_per_day=_per_day_limit(room, si), room_rent_clause=room.id if room else None,
        icu_limit_per_day=_per_day_limit(icu, si), icu_clause=icu.id if icu else None,
        proportionate_clause=prop.id if prop else None, proportionate_exclusions=exclusions,
        copay_percent=Decimal(copay_pct) if copay_pct else None, copay_condition=copay_cond,
        copay_clause=copay.id if copay_pct else None,
        non_payable_items=non_payable, non_payable_clause=nonpay.id if nonpay else None,
        sub_limits=sub_limits,
        clauses=clauses,
    )
    warnings = []
    if len(clauses) <= 1:
        warnings.append("no numbered clauses recognised; clause citations will not be available")
    if doc.room_rent_limit_per_day is None:
        warnings.append("room-rent limit not found")
    return doc, warnings
