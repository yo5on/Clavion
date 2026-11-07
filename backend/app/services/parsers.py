"""Local deterministic parsers: plain text -> validated Pydantic documents. No model is involved.

They target the layouts Indian hospital bills, policy wordings and settlement letters commonly use (labelled
header fields, one line item per line, numbered clauses, per-head settlement tables). Anything they miss is left
null and flagged, and the user corrects it on the review screen.

Every value they set is recorded in `Extraction.fields` with its status and source location:
  extracted  read from a labelled field or a table row; the source line is given
  inferred   derived by a heuristic (e.g. the hospital name taken from the first line mentioning a hospital, a
             quantity worked out from amount / rate, a limit computed from a percentage of the sum insured)
  missing    not found; the value is null and nothing is guessed
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from ..schemas.bill import BillLineItem, HospitalBill
from ..schemas.claim import (FieldMeta, PolicyClause, PolicyDocument, SettlementDeduction, SettlementLetter,
                             SourceRef, SubLimit)

# Plain integers without a comma or decimals (e.g. "26000") are only read as money on a bill line that proves
# itself, "qty x rate = amount" with exact arithmetic (INT_ITEM_RE), or after a rupee sign; elsewhere they are too
# ambiguous (years, codes, pin codes).
MONEY = r"(?:\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{1,2})"
RS = r"(?:Rs\.?|INR|₹)"
# Indian documents often write large amounts as "Rs 5 lakh" or "Rs 1.5 crore"; money() applies the multiplier.
UNIT = r"(?:\s*(?:lakhs?|lacs?|crores?)\b)?"
RS_AMOUNT = rf"{RS}\s*((?:{MONEY}|\d+){UNIT})"
DATE = r"\d{1,2}[-/. ](?:[A-Za-z]{3,9}|\d{1,2})[-/. ]\d{2,4}"
SYNTHETIC_MARKER = "SYNTHETIC TEST DOCUMENT"
PAGE_BREAK = "\f"


def is_synthetic(text: str) -> bool:
    """True if the document carries the synthetic-test marker. Ignores spacing and punctuation, which OCR of a poor
    scan often drops ("SYNTHETICTESTDOCUMENT-NOTAREAL"), so a synthetic scan is never labelled as a real document."""
    return re.sub(r"[^A-Z]", "", SYNTHETIC_MARKER) in re.sub(r"[^A-Z]", "", text.upper())


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


UNIT_MULTIPLIER = {"lakh": 100_000, "lac": 100_000, "crore": 10_000_000}


def money(s: str) -> Decimal:
    m = re.fullmatch(r"([\d,.]+)\s*([a-z]*?)s?", s.strip(), re.I)
    if not m:
        return Decimal(s.replace(",", ""))
    return Decimal(m.group(1).replace(",", "")) * UNIT_MULTIPLIER.get(m.group(2).lower(), 1)


def categorize(description: str) -> str:
    d = description.lower()
    return next((cat for cat, pat in CATEGORIES if re.search(pat, d)), "other")


DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y",
                "%d-%m-%y", "%d-%b-%y", "%d.%b.%Y", "%d/%b/%Y")


def parse_date(s: str | None) -> date | None:
    """Dates as printed on Indian documents. Numeric dates are read day-first (dd/mm/yyyy), as is the convention."""
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.strip())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- lines and source locations

class Line(str):
    """A normalised text line that remembers where it came from: page (1-based), line within the page (1-based,
    counting blank lines) and the raw text as extracted."""

    page: int
    no: int
    raw: str


def _normalise(ln: str) -> str:
    ln = re.sub(r"[ \t]+", " ", ln).strip()
    # "Rs 1,500/-" -> "Rs 1,500.00"; "1,500.50/-" keeps its paise
    return re.sub(r"(\d)(\.\d{1,2})?\s*/-", lambda m: m[1] + (m[2] or ".00"), ln)


def _lines(text: str) -> list[Line]:
    out = []
    for p, page in enumerate(text.split(PAGE_BREAK), 1):
        for n, raw in enumerate(page.split("\n"), 1):
            if raw.strip():
                ln = Line(_normalise(raw))
                ln.page, ln.no, ln.raw = p, n, raw.strip()
                out.append(ln)
    return out


@dataclass
class Extraction:
    doc: BaseModel
    warnings: list[str]
    fields: dict[str, FieldMeta] = field(default_factory=dict)


class _Rec:
    """Records the status and source of every field a parser sets."""

    def __init__(self, text: str):
        self.text, self.fields = text, {}
        self.offsets = []  # (start offset, page, line no, raw line) for each line
        pos = 0
        for p, page in enumerate(text.split(PAGE_BREAK), 1):
            for n, raw in enumerate(page.split("\n"), 1):
                self.offsets.append((pos, p, n, raw.strip()))
                pos += len(raw) + 1  # the "\n" or "\f" that follows

    def at(self, pos: int) -> SourceRef:
        lo, hi = 0, len(self.offsets) - 1
        while lo < hi:  # last line starting at or before pos
            mid = (lo + hi + 1) // 2
            if self.offsets[mid][0] <= pos:
                lo = mid
            else:
                hi = mid - 1
        _, p, n, raw = self.offsets[lo]
        return SourceRef(page=p, line=n, text=raw[:300])

    @staticmethod
    def src(line: Line) -> SourceRef:
        return SourceRef(page=line.page, line=line.no, text=line.raw[:300])

    def put(self, path: str, status: str, source: SourceRef | None = None, note: str | None = None):
        self.fields[path] = FieldMeta(status=status, source=source, note=note)

    def search(self, path: str, pattern: str, flags=re.I | re.M) -> str | None:
        m = re.search(pattern, self.text, flags)
        if not m:
            return None
        self.put(path, "extracted", self.at(m.start(1)))
        return m.group(1).strip()

    def amount_after(self, path: str, label: str) -> Decimal | None:
        v = self.search(path, rf"{label}\s*(?:\({RS}\))?\s*[:\-]?\s*{RS}?\s*((?:{MONEY}|\d+){UNIT})")
        return money(v) if v else None

    def first_line(self, path: str, lines: list[Line], pred, note: str) -> str | None:
        ln = next((ln for ln in lines if pred(ln)), None)
        if ln is None:
            return None
        self.put(path, "inferred", self.src(ln), note)
        return str(ln)

    def finish(self, doc: BaseModel, prefix: str = "") -> None:
        """Every scalar field still null is recorded as missing."""
        for name, value in doc:
            path = prefix + name
            if path not in self.fields and value is None:
                self.put(path, "missing")


# ---------------------------------------------------------------- hospital bill

ITEM_RE = re.compile(
    rf"^(?:\d{{1,3}}(?:[.)]\s*|\s+)(?=[A-Za-z]))?(?P<desc>.*?[A-Za-z].*?)\s+"
    # rate and amount must be separated (space or "="): otherwise "4,800.00" splits into rate "4,80" + amount "0.00"
    rf"(?:(?P<qty>\d+(?:\.\d+)?)\s*(?:[xX×*]\s*|\s+))?(?:(?P<rate>{MONEY})(?:\s*=\s*|\s+))?(?P<amt>{MONEY})$")
INT_ITEM_RE = re.compile(
    r"^(?:\d{1,3}[.)]\s*)?(?P<desc>.*?[A-Za-z].*?)\s+(?P<qty>\d+)\s*[xX×*]\s*(?P<rate>\d+(?:\.\d{1,2})?)\s*=\s*"
    r"(?P<amt>\d+(?:\.\d{1,2})?)$")
GRAND_TOTAL_RE = re.compile(r"grand[\s.]*total|net\s*(?:amount|payable|bill)|total\s*(?:amount|bill)|bill\s*total"
                            r"|total\s*payable", re.I)
TOTAL_RE = re.compile(rf"{GRAND_TOTAL_RE.pattern}|^\W*total\b", re.I)
# A line that carries a money-like figure ("3,000.00", OCR'd "12:000.00") is probably a bill item even if unreadable.
FIGURE_RE = re.compile(r"\d[\d,.:]*[.,:]\d{2}\b")
SKIP_RE = re.compile(r"sub\s*-?\s*total|page\s*total|carried\s*(?:forward|over)|brought\s*forward|b/f\b|c/f\b"
                     r"|discount|advance|deposit|paid|balance|tax|gst|amount\s*in\s*words|rupees\s+\w+\s+only", re.I)
ADMIT_RE = rf"(?:Date\s*of\s*Admission|Admission\s*Date|\bDOA\b|Admitted\s*on)\s*[:\-]?\s*({DATE})"
DISCHARGE_RE = rf"(?:Date\s*of\s*Discharge|Discharge\s*Date|\bDOD\b|Discharged\s*on)\s*[:\-]?\s*({DATE})"
PATIENT_RE = r"Patient(?:'?s)?(?:\s*Name)?\s*[:\-]\s*([A-Za-z][A-Za-z .']*?)(?:\s{2,}|\s*$|\s+(?:Age|UHID|IP\s*No))"


def extract_bill(text: str) -> Extraction:
    rec, lines = _Rec(text), _lines(text)
    items: list[BillLineItem] = []
    totals: list[tuple[int, Decimal, Line]] = []  # (priority, amount, line); a grand total beats a plain "Total"
    skipped = []
    for ln in lines:
        if TOTAL_RE.search(ln) and not SKIP_RE.search(ln):
            if amts := re.findall(MONEY, ln) or re.findall(r"\b\d{3,}\b", ln):
                totals.append((2 if GRAND_TOTAL_RE.search(ln) else 1, money(amts[-1]), ln))
            continue
        if SKIP_RE.search(ln):
            continue
        if not (m := ITEM_RE.match(ln)):
            m = INT_ITEM_RE.match(ln)
            if m and Decimal(m["qty"]) * Decimal(m["rate"]) != Decimal(m["amt"]):
                skipped.append(f"page {ln.page} line {ln.no} '{ln}' not read: {m['qty']} x {m['rate']} does not "
                               f"equal {m['amt']}")
                continue
            if not m:
                if FIGURE_RE.search(ln) and re.search(r"[A-Za-z]{3}", ln):
                    skipped.append(f"page {ln.page} line {ln.no} '{ln}' looks like a bill item but could not be "
                                   f"read; add it on the review screen")
                continue
        i = len(items)
        amount = money(m["amt"])
        rate = money(m["rate"]) if m["rate"] else None
        qty = Decimal(m["qty"]) if m["qty"] else None
        rec.put(f"line_items.{i}", "extracted", rec.src(ln))
        if qty is None and rate:  # OCR often misses short qty values; infer when it is a whole number
            q = amount / rate
            if q == q.to_integral_value() and q > 0:
                qty = q
                rec.put(f"line_items.{i}.quantity", "inferred", rec.src(ln),
                        f"not printed; worked out as amount / rate = {amount} / {rate}")
        desc = m["desc"].strip(" -:.")
        if FIGURE_RE.search(desc):  # a figure left inside the description means the columns were misread
            skipped.append(f"page {ln.page} line {ln.no} '{ln}': description contains a figure, so the amount may be "
                           f"misread; check it")
        items.append(BillLineItem(description=desc, quantity=qty, unit_price=rate, amount=amount,
                                  category=categorize(desc)))
        rec.put(f"line_items.{i}.category", "inferred", rec.src(ln), "assigned from the description's wording")
    total = None
    if totals:
        best = max(t[0] for t in totals)
        prio, total, tline = [t for t in totals if t[0] == best][-1]  # the last grand total on the document
        rec.put("total_amount", "extracted", rec.src(tline))
    bill = HospitalBill(
        hospital_name=rec.first_line("hospital_name", lines, lambda ln: re.search(
            r"hospital|medical|clinic|nursing home|institute", ln, re.I) and not re.search(r"bill|:", ln, re.I)
            and not is_synthetic(ln), "taken from the first line that names a hospital"),
        bill_number=rec.search("bill_number", r"Bill\s*No\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*?)(?=\s|$|Bill|Date)"),
        patient_name=rec.search("patient_name", PATIENT_RE),
        bill_date=rec.search("bill_date", rf"Bill\s*Date\s*[:\-]?\s*({DATE})"),
        admission_date=rec.search("admission_date", ADMIT_RE),
        discharge_date=rec.search("discharge_date", DISCHARGE_RE),
        line_items=items,
        total_amount=total,
    )
    rec.finish(bill)
    warnings = skipped + bill.arithmetic_issues()
    if not items:
        warnings.append("no line items recognised; add them on the review screen")
    if len(totals) > 1 and len({t[1] for t in totals}) > 1:
        warnings.append(f"several totals printed ({', '.join(str(t[1]) for t in totals)}); used {total} from page "
                        f"{tline.page} line {tline.no}")
    return Extraction(bill, warnings, rec.fields)


def parse_bill(text: str) -> tuple[HospitalBill, list[str]]:
    x = extract_bill(text)
    return x.doc, x.warnings


# ---------------------------------------------------------------- settlement letter

DEDUCTION_RE = re.compile(
    rf"^(?:\d{{1,3}}[.)]\s*)?(?P<desc>.*?[A-Za-z].*?)\s*[:\-]?\s*(?:{RS}\s*(?P<int>\d+)|{RS}?\s*(?P<amt>{MONEY}))$")
# Per-head table row: "Room Rent  40,000.00  20,000.00  20,000.00  Room rent capped (Clause 3.1)". Read only when
# claimed - approved = deducted holds exactly, so the columns prove their own meaning.
TABLE_ROW_RE = re.compile(rf"^(?:\d{{1,3}}[.)]\s*)?(?P<desc>[A-Za-z][^0-9]*?)\s+(?P<a>{MONEY})\s+(?P<b>{MONEY})\s+"
                          rf"(?P<c>{MONEY})(?:\s+(?P<reason>.*))?$")
SECTION_END_RE = re.compile(r"total\s*deduct|amount\s*(?:approved|settled|payable|paid)|approved\s*amount", re.I)
CLAUSE_REF_RE = r"(?:Clause|Section|Cl\.)\s*(\d+(?:\.\d+)*)"


def extract_settlement(text: str) -> Extraction:
    rec, lines = _Rec(text), _lines(text)
    deductions: list[SettlementDeduction] = []
    warnings: list[str] = []
    in_section = False
    for ln in lines:
        if re.match(r"^(?:details\s+of\s+)?(?:deductions?|disallowances?)\b[^0-9]*$", ln, re.I):
            in_section = True
            continue
        if in_section and SECTION_END_RE.search(ln):
            in_section = False
            continue
        if not in_section:
            continue
        if m := DEDUCTION_RE.match(ln):
            desc = m["desc"].strip(" -:.")
            rec.put(f"deductions.{len(deductions)}", "extracted", rec.src(ln))
            deductions.append(SettlementDeduction(description=desc, amount=money(m["amt"] or m["int"]),
                                                  clause_ref=_clause(desc)))
        elif re.search(r"[A-Za-z]{4}", ln) and not re.search(r"\bamount\b.*\breason\b|^description\b", ln, re.I):
            warnings.append(f"page {ln.page} line {ln.no} '{ln}' in the deductions section has no amount that could "
                            f"be read; add it on the review screen if it is a deduction")

    if not deductions:  # fall back to a per-head table (claimed / approved / deducted columns)
        for ln in lines:
            m = TABLE_ROW_RE.match(ln)
            if not m or re.search(r"\btotal\b", m["desc"], re.I):
                continue
            a, b, c = money(m["a"]), money(m["b"]), money(m["c"])
            if a - b != c or c <= 0:
                continue
            reason = (m["reason"] or "").strip(" -:.")
            desc = f"{m['desc'].strip(' -:.')} - {reason}" if reason else m["desc"].strip(" -:.")
            rec.put(f"deductions.{len(deductions)}", "extracted", rec.src(ln),
                    f"table row: claimed {a} - approved {b} = deducted {c}")
            deductions.append(SettlementDeduction(description=desc, amount=c, clause_ref=_clause(desc)))
    for i, d in enumerate(deductions):
        if d.clause_ref:
            rec.put(f"deductions.{i}.clause_ref", "extracted", rec.fields[f"deductions.{i}"].source)

    letter = SettlementLetter(
        insurer_name=rec.first_line("insurer_name", lines, lambda ln: re.search(r"insurance|assurance", ln, re.I)
                                    and not is_synthetic(ln), "taken from the first line that names an insurer"),
        claim_number=rec.search("claim_number", r"Claim\s*(?:No|Number|ID|Ref)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)"),
        policy_number=rec.search("policy_number", r"Policy\s*(?:No|Number)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)"),
        patient_name=rec.search("patient_name", PATIENT_RE),
        hospital_name=rec.search("hospital_name", r"Hospital(?:\s*Name)?\s*[:\-]\s*(.+?)(?:\s{2,}|\s*$)"),
        claimed_amount=rec.amount_after("claimed_amount", r"(?:Amount\s*Claimed|Claimed\s*Amount|Claim\s*Amount)"),
        approved_amount=rec.amount_after(
            "approved_amount", r"(?:Amount\s*(?:Approved|Settled|Payable)|(?:Approved|Settled)\s*Amount"
                               r"|Net\s*Amount\s*Payable)"),
        paid_amount=rec.amount_after("paid_amount", r"(?:Net\s*)?(?:Amount\s*(?:Paid|Transferred|Disbursed)|Paid\s*Amount"
                                                    r"|NEFT\s*Amount)"),
        total_deductions=rec.amount_after("total_deductions", r"Total\s*(?:Deductions?|Disallowances?|Amount\s*"
                                                              r"Deducted)"),
        deductions=deductions,
    )
    rec.finish(letter)
    if not deductions:
        warnings.append("no itemised deductions recognised; add them on the review screen")
    for f in ("claimed_amount", "approved_amount"):
        if getattr(letter, f) is None:
            warnings.append(f"{f.replace('_', ' ')} not found")
    return Extraction(letter, warnings, rec.fields)


def _clause(desc: str) -> str | None:
    m = re.search(CLAUSE_REF_RE, desc, re.I)
    return m.group(1) if m else None


def parse_settlement(text: str) -> tuple[SettlementLetter, list[str]]:
    x = extract_settlement(text)
    return x.doc, x.warnings


# ---------------------------------------------------------------- policy wording

CLAUSE_RE = re.compile(r"^(?:(?:Clause|Section)\s+)?(\d{1,2}(?:\.\d{1,2})*)[.)]?\s+([A-Z(].*)$")
ANNEX_RE = re.compile(r"^((?:Annexure|Schedule|Appendix)\s*[\w-]*)\s*[:\-]?\s*(.*)$", re.I)
ROOM_CATEGORY_RE = r"(single\s+(?:private\s+)?(?:a/?c\s+)?room|private\s+room|semi[- ]private|shared\s+room|" \
                   r"twin[- ]sharing|general\s+ward|deluxe|suite)"


def split_clauses(text: str, rec: _Rec | None = None) -> list[PolicyClause]:
    clauses: list[PolicyClause] = []
    cur_id, cur_title, buf, head = "preamble", "Preamble", [], None

    def flush():
        if buf:
            if rec:
                rec.put(f"clauses.{len(clauses)}", "extracted", rec.src(head))
            clauses.append(PolicyClause(id=cur_id, title=cur_title, text="\n".join(buf)))

    for ln in _lines(text):
        m = CLAUSE_RE.match(ln) or ANNEX_RE.match(ln)
        if m:
            flush()
            cur_id, rest, head = m.group(1), m.group(2), ln
            cur_title = re.split(r"[:.]\s", rest, maxsplit=1)[0][:80] or cur_id
            buf = [str(ln)]
        else:
            head = head or ln  # the preamble starts at the document's first line
            buf.append(str(ln))
    flush()
    return clauses


def _find_clause(clauses, title_pat: str, text_pat: str | None = None, exclude: str | None = None):
    for fld in ("title", "text"):
        for c in clauses:
            hay = c.title if fld == "title" else c.text
            if re.search(title_pat, hay, re.I) and (not exclude or not re.search(exclude, c.title, re.I)) \
                    and (not text_pat or re.search(text_pat, c.text, re.I)):
                return c
    return None


def _per_day_limit(c: PolicyClause | None, sum_insured: Decimal | None) -> tuple[Decimal | None, str | None]:
    """(limit per day, how it was derived). Limit = the smaller of an explicit 'Rs X per day' and 'Y% of Sum
    Insured', when both are given."""
    if not c:
        return None, None
    text = c.text.replace("\n", " ")
    explicit = [money(v) for v in re.findall(rf"{RS_AMOUNT}\s*(?:per|a|/)\s*day", text, re.I)]
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(?:the\s*)?sum\s*insured", text, re.I)
    from_pct = (Decimal(pct.group(1)) / 100 * sum_insured).quantize(Decimal("0.01")) if pct and sum_insured else None
    candidates = explicit + ([from_pct] if from_pct is not None else [])
    if not candidates:
        return None, None
    limit = min(candidates)
    if from_pct is not None and (not explicit or from_pct < min(explicit)):
        how = f"{pct.group(1)}% of the sum insured Rs {sum_insured:,} = Rs {from_pct:,}"
        how += f" (lower than the stated maximum Rs {min(explicit):,})" if explicit else ""
        return limit, how
    return limit, None


def _bullets(c: PolicyClause) -> list[str]:
    return [re.sub(r"^[-•*–]\s*", "", ln).strip() for ln in c.text.splitlines()[1:] if re.match(r"^[-•*–]", ln)]


def extract_policy(text: str) -> Extraction:
    rec, lines = _Rec(text), _lines(text)
    clauses = split_clauses(text, rec)
    clause_src = {c.id: rec.fields[f"clauses.{i}"].source for i, c in enumerate(clauses)}
    si = rec.amount_after("sum_insured", r"Sum\s+Insured")
    room = _find_clause(clauses, r"room\s*rent", r"per\s*day|%\s*of", exclude=r"icu|intensive|proportion") \
        or next((c for c in clauses if re.search(r"room\s*rent", c.title, re.I)  # category-only limit
                 and not re.search(r"icu|intensive|proportion", c.title, re.I)), None)
    icu = _find_clause(clauses, r"\bicu\b|intensive\s*care", r"per\s*day")
    prop = _find_clause(clauses, r"proportion")
    copay = _find_clause(clauses, r"co-?\s*pay")
    nonpay = _find_clause(clauses, r"non[- ]?payable|not\s+payable")
    subl = _find_clause(clauses, r"sub[- ]?limit")

    def from_clause(path: str, c: PolicyClause | None, status="extracted", note=None):
        if c:
            rec.put(path, status, clause_src.get(c.id), note)

    room_limit, room_how = _per_day_limit(room, si)
    room_category = None
    if room and room_limit is None and (m := re.search(ROOM_CATEGORY_RE, room.text, re.I)):
        room_category = m.group(1)
        from_clause("room_rent_category", room)
        rec.put("room_rent_limit_per_day", "missing", clause_src.get(room.id),
                f"Clause {room.id} limits the room category ({room_category}), not an amount per day")
    elif room_limit is not None:
        from_clause("room_rent_limit_per_day", room, "inferred" if room_how else "extracted", room_how)
    icu_limit, icu_how = _per_day_limit(icu, si)
    if icu_limit is not None:
        from_clause("icu_limit_per_day", icu, "inferred" if icu_how else "extracted", icu_how)

    exclusions: list[str] = []
    if prop and (m := re.search(r"not\s+(?:be\s+)?appl(?:y|icable)\s+to\s+([^.]+)", prop.text.replace("\n", " "),
                                re.I)):
        exclusions = sorted({cat for word, cat in EXCLUSION_WORDS.items() if word in m.group(1).lower()})
        from_clause("proportionate_exclusions", prop, "inferred", f"read from: '{m.group(0)[:120]}'")

    sub_limits = []
    if subl:
        for b in _bullets(subl):
            if m := re.match(rf"(.+?)\s*[:\-–]\s*(?:up\s*to\s*)?{RS_AMOUNT}", b, re.I):
                from_clause(f"sub_limits.{len(sub_limits)}", subl)
                sub_limits.append(SubLimit(name=m.group(1).strip(), limit=money(m.group(2)), clause_id=subl.id))

    non_payable = []
    if nonpay:
        non_payable = _bullets(nonpay)
        if non_payable:
            from_clause("non_payable_items", nonpay)
        else:
            non_payable = [s.strip() for s in re.split(r",|;|\band\b", nonpay.text.split(":", 1)[-1])
                           if 2 < len(s.strip()) < 60]
            from_clause("non_payable_items", nonpay, "inferred", "split from running text at commas and 'and'")

    excl = next((c for c in clauses if re.search(r"exclusion", c.title, re.I)), None)
    excluded_items = []
    if excl:
        excluded_items = _bullets(excl)
        if excluded_items:
            from_clause("exclusions", excl)
        else:
            excluded_items = [s.strip() for s in re.split(r",|;", excl.text.split(":", 1)[-1]) if 2 < len(s.strip()) < 80]
            from_clause("exclusions", excl, "inferred", "split from running text at commas")
        from_clause("exclusions_clause", excl)

    copay_pct = (re.search(r"co-?\s*pay(?:ment)?\s*(?:of|:|at)?\s*(\d+(?:\.\d+)?)\s*%", copay.text, re.I)
                 or re.search(r"(\d+(?:\.\d+)?)\s*%\s*co-?\s*pay", copay.text, re.I)) if copay else None
    copay_cond = None
    if copay_pct:
        from_clause("copay_percent", copay)
        if m := re.search(r"((?:where|if|for|in\s+case)\s[^.]+)", " ".join(copay.text.split("\n")[1:]), re.I):
            copay_cond = m.group(1).strip()
            from_clause("copay_condition", copay)
    for path, c in (("room_rent_clause", room), ("icu_clause", icu),
                    ("proportionate_clause", prop), ("copay_clause", copay if copay_pct else None),
                    ("non_payable_clause", nonpay)):
        from_clause(path, c)

    doc = PolicyDocument(
        policy_name=rec.first_line("policy_name", lines, lambda ln: not is_synthetic(ln),
                                   "taken from the first line of the document"),
        policy_number=rec.search("policy_number", r"Policy\s*(?:No|Number)\.?\s*[:\-]?\s*([A-Z0-9][\w/\-]*)"),
        sum_insured=si,
        room_rent_limit_per_day=room_limit, room_rent_clause=room.id if room else None,
        room_rent_category=room_category,
        icu_limit_per_day=icu_limit, icu_clause=icu.id if icu else None,
        proportionate_clause=prop.id if prop else None, proportionate_exclusions=exclusions,
        copay_percent=Decimal(copay_pct.group(1)) if copay_pct else None, copay_condition=copay_cond,
        copay_clause=copay.id if copay_pct else None,
        non_payable_items=non_payable, non_payable_clause=nonpay.id if nonpay else None,
        exclusions=excluded_items, exclusions_clause=excl.id if excl else None,
        sub_limits=sub_limits,
        clauses=clauses,
    )
    rec.finish(doc)
    warnings = []
    if len(clauses) <= 1:
        warnings.append("no numbered clauses recognised; clause citations will not be available")
    if doc.room_rent_limit_per_day is None:
        warnings.append(f"room-rent limit is a room category ({room_category}), not an amount per day"
                        if room_category else "room-rent limit not found")
    return Extraction(doc, warnings, rec.fields)


def parse_policy(text: str) -> tuple[PolicyDocument, list[str]]:
    x = extract_policy(text)
    return x.doc, x.warnings


EXTRACTORS = {"bill": extract_bill, "policy": extract_policy, "settlement": extract_settlement}
