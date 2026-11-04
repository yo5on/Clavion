"""Appeal letter (local template, filled only from audit findings) and PDF export (fpdf2, core fonts)."""

from decimal import Decimal

from fpdf import FPDF

from ..schemas.claim import AuditReport, SettlementLetter

DEMO_BANNER = "DEMO - SYNTHETIC DATA. NOT A REAL CLAIM."
DISCLAIMER = ("Clavion explains settlements using the uploaded documents. It is not legal advice and does not "
              "guarantee that any amount will be recovered.")


def _rs(v: Decimal | None) -> str:
    return "-" if v is None else f"Rs {v:,.2f}"


def appeal_letter(report: AuditReport, s: SettlementLetter | None, patient: str | None) -> str:
    s = s or SettlementLetter()
    contest = [f for f in report.findings if f.status == "contestable"]
    unverified = [f for f in report.findings if f.status == "unverified"]
    name = patient or s.patient_name or "[Policyholder name]"
    out = []
    if report.demo:
        out += [DEMO_BANNER, ""]
    out += [
        "To,", f"The Grievance Redressal Officer{', ' + s.insurer_name if s.insurer_name else ''}", "",
        f"Subject: Request for review of claim settlement - Claim No. {s.claim_number or '[claim number]'}, "
        f"Policy No. {s.policy_number or '[policy number]'}", "",
        "Dear Sir/Madam,", "",
        f"I write about the settlement of the above claim for treatment of {name}"
        f"{' at ' + s.hospital_name if s.hospital_name else ''}. The claim of {_rs(report.claimed_amount)} was "
        f"settled for {_rs(report.approved_amount)}, with deductions of {_rs(report.total_deductions)}. I have "
        f"compared the deductions with my policy wording and the hospital bill, and request that you review the "
        f"following.", "",
    ]
    if contest:
        out.append("Deductions not supported by the policy wording:")
        for i, f in enumerate(contest, 1):
            refs = ", ".join(e.ref for e in f.evidence if e.doc_type == "policy" and e.found)
            out.append(f"{i}. {f.description} - deducted {_rs(f.insurer_amount)}. {f.explanation}"
                       f"{' (See ' + refs + '.)' if refs else ''} I request reconsideration of "
                       f"{_rs(f.contestable_amount)}.")
            out += [f"   Calculation: {step}" for step in f.calculation]
        out.append("")
    if unverified:
        out.append("Deductions that need an explanation:")
        for f in unverified:
            out.append(f"- {f.description} ({_rs(f.insurer_amount)}): please state the policy clause and the "
                       f"calculation applied.")
        out.append("")
    out += [
        f"I request reconsideration of {_rs(report.contestable_total)}"
        + (f" and a written explanation for {_rs(report.unverified_total)}" if unverified else "")
        + ", and a reply within the timelines set by the applicable IRDAI grievance redressal guidelines. If the "
          "matter is not resolved, I may approach the Insurance Ombudsman.", "",
        "Enclosures: hospital bill, claim settlement letter, policy wording.", "",
        "Yours faithfully,", name,
    ]
    return "\n".join(out)


def _latin1(s: str) -> str:
    return s.replace("₹", "Rs ").replace("–", "-").replace("’", "'").encode("latin-1", "replace").decode("latin-1")


class _PDF(FPDF):
    def __init__(self, title: str, demo: bool):
        super().__init__()
        self.doc_title, self.demo = title, demo
        self.set_auto_page_break(True, 18)
        self.set_margins(16, 16)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(11, 16, 38)
        self.cell(0, 6, "CLAVION", new_x="LMARGIN", new_y="NEXT")
        if self.demo:
            self.set_text_color(185, 28, 28)
            self.cell(0, 5, DEMO_BANNER, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(100, 100, 100)
        self.multi_cell(0, 3.5, _latin1(f"{DISCLAIMER}  Page {self.page_no()}"))

    def para(self, text: str, size=9.5, style=""):
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, 5, _latin1(text), new_x="LMARGIN", new_y="NEXT")


def build_pdf(kind: str, title: str, report: AuditReport, appeal: str | None) -> bytes:
    pdf = _PDF(title, report.demo)
    pdf.add_page()
    if kind == "appeal":
        pdf.para(appeal or "")
        return bytes(pdf.output())

    pdf.para(f"Claim audit report: {title}", 14, "B")
    pdf.para(f"Method: {report.method}. Generated {report.generated_at}.", 8)
    pdf.ln(2)
    for label, v in [("Hospital bill (sum of lines)", report.bill_total), ("Amount claimed", report.claimed_amount),
                     ("Amount approved", report.approved_amount), ("Total deductions", report.total_deductions),
                     ("Supported by documents", report.supported_total),
                     ("Potentially contestable", report.contestable_total),
                     ("Needs explanation (unverified)", report.unverified_total)]:
        pdf.set_font("Helvetica", "", 9.5)
        pdf.cell(80, 5.5, label)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.cell(0, 5.5, _latin1(_rs(v)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.para("Findings", 12, "B")
    for f in report.findings:
        pdf.ln(1)
        pdf.para(f"{f.id}. {f.description}  [{f.status.upper()}]", 10, "B")
        pdf.para(f"Category: {f.category}. Deducted {_rs(f.insurer_amount)}; supported {_rs(f.supported_amount)}; "
                 f"contestable {_rs(f.contestable_amount)}.", 9)
        pdf.para(f.explanation, 9)
        for step in f.calculation:
            pdf.para(f"  - {step}", 8.5)
        for e in f.evidence:
            pdf.para(f"  Evidence ({e.doc_type}, {e.ref}{'' if e.found else ', NOT FOUND'}): "
                     f"{e.excerpt[:300]}", 8)
    if report.missing_information:
        pdf.ln(2)
        pdf.para("Missing or inconsistent information", 12, "B")
        for m in report.missing_information:
            pdf.para(f"- {m}", 9)
    if appeal:
        pdf.add_page()
        pdf.para("Appeal letter", 12, "B")
        pdf.para(appeal)
    return bytes(pdf.output())
