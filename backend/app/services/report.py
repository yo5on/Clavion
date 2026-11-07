"""Appeal letter (local template, built statement by statement from audit findings) and PDF export (fpdf2).

Every appeal statement is labelled with what it rests on (see schemas.claim.AppealStatement): a fact from an
uploaded document, a Clavion recalculation, suggested wording, or letter formalities. The policyholder can edit or
drop any statement before export. Nothing here makes a legal claim; the letter asks for review and explanation.
"""

from fpdf import FPDF

from .currency import rs
from ..schemas.claim import AppealStatement, AuditReport, Evidence, Finding, SettlementLetter

DEMO_BANNER = "DEMO - SYNTHETIC DATA. NOT A REAL CLAIM."
DISCLAIMER = ("Clavion explains settlements using the uploaded documents. It is not legal advice and does not "
              "guarantee that any amount will be recovered.")
DOC_LABELS = {"bill": "Hospital bill", "policy": "Policy wording", "settlement": "Settlement letter"}
APPEAL_SOURCE = "Local template filled from audit findings (no AI)"


def ref(e: Evidence) -> str:
    where = f", page {e.source.page} line {e.source.line}" if e.source else ""
    return f"{DOC_LABELS[e.doc_type]}: {e.ref}{where}"


def appeal_statements(report: AuditReport, s: SettlementLetter | None, patient: str | None) -> list[AppealStatement]:
    s = s or SettlementLetter()
    contest = [f for f in report.findings if f.status == "contestable"]
    unverified = [f for f in report.findings if f.status == "unverified"]
    name = patient or s.patient_name or "[Policyholder name]"
    out: list[AppealStatement] = []

    def add(section, kind, text, refs=(), finding: Finding | None = None):
        out.append(AppealStatement(id=f"s{len(out) + 1}", section=section, kind=kind, text=text, refs=list(refs),
                                   finding_id=finding.id if finding else None))

    if report.demo:
        add("Header", "standard", DEMO_BANNER)
    add("Header", "standard", f"To,\nThe Grievance Redressal Officer{', ' + s.insurer_name if s.insurer_name else ''}")
    add("Header", "standard", f"Subject: Request for review of claim settlement - Claim No. "
                              f"{s.claim_number or '[claim number]'}, Policy No. {s.policy_number or '[policy number]'}")
    add("Header", "standard", "Dear Sir/Madam,")
    add("Claim", "source_fact",
        f"I write about the settlement of the above claim for treatment of {name}"
        f"{' at ' + s.hospital_name if s.hospital_name else ''}. The claim of {rs(report.claimed_amount)} was "
        f"settled for {rs(report.approved_amount)}, with deductions of {rs(report.total_deductions)}.",
        ["Settlement letter: claimed and approved amounts"])
    if contest or unverified:
        add("Claim", "suggestion", "I have compared the deductions with my policy wording and the hospital bill, and "
                                   "request that you review the following.")
    for i, f in enumerate(contest, 1):
        sec = f"Deduction {f.id}: {f.description}"
        insurer_ev = next((e for e in f.evidence if e.doc_type == "settlement"), None)
        add(sec, "source_fact", f"{i}. The settlement letter deducts {rs(f.insurer_amount)} as \"{f.description}\".",
            [ref(insurer_ev)] if insurer_ev else [], f)
        clause_ev = next((e for e in f.evidence if e.doc_type == "policy" and e.found
                          and f.policy_clause and f.policy_clause.startswith(e.ref)), None)
        if clause_ev:
            wording = " ".join(clause_ev.excerpt.split("\n")[1:]).strip() or clause_ev.excerpt
            add(sec, "source_fact", f"{f.policy_clause} of the policy states: \"{wording[:600]}\"", [ref(clause_ev)], f)
        bill_refs = [ref(e) for e in f.evidence if e.doc_type == "bill"][:6]
        if f.calculation:
            add(sec, "calculation", "Recalculated from the bill and the policy: " + "; ".join(f.calculation) + ".",
                bill_refs, f)
        add(sec, "suggestion", f"{f.contestable_reason or f.explanation} I request reconsideration of "
                               f"{rs(f.contestable_amount)}.", [], f)
    if unverified:
        for f in unverified:
            sec = f"Deduction {f.id}: {f.description}" if f.rule_id != "R-REC-01" else "Unexplained difference"
            text = (f"The settlement reduces the claim by {rs(f.insurer_amount)} more than the itemised deductions. "
                    f"Please itemise this amount and state the clause applied." if f.rule_id == "R-REC-01" else
                    f"\"{f.description}\" ({rs(f.insurer_amount)}): please state the policy clause and the "
                    f"calculation applied" + (f", and provide {'; '.join(f.missing)}." if f.missing else "."))
            add(sec, "suggestion", text, [], f)
    if contest or unverified:
        add("Request", "suggestion",
            f"I request reconsideration of {rs(report.contestable_total)}"
            + (f" and a written explanation for {rs(report.unverified_total)}" if unverified else "")
            + ", and a reply within the timelines set by the applicable IRDAI grievance redressal guidelines. If the "
              "matter is not resolved, I may approach the Insurance Ombudsman.")
    add("Closing", "standard", "Enclosures: hospital bill, claim settlement letter, policy wording.")
    add("Closing", "standard", f"Yours faithfully,\n{name}")
    return out


def compose(statements: list[AppealStatement]) -> str:
    """Letter text from the included statements; a blank line between sections."""
    out, section = [], None
    for st in statements:
        if not st.include or not st.text.strip():
            continue
        if section is not None and st.section != section:
            out.append("")
        elif section is not None and st.kind == "standard":
            out.append("")
        out.append(st.text.strip())
        section = st.section
    return "\n".join(out)


def appeal_letter(report: AuditReport, s: SettlementLetter | None, patient: str | None) -> str:
    return compose(appeal_statements(report, s, patient))


def _latin1(s: str) -> str:
    return s.replace("₹", "Rs ").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"') \
        .encode("latin-1", "replace").decode("latin-1")


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


STATUS_WORDS = {"supported": "SUPPORTED", "contestable": "POTENTIALLY CONTESTABLE", "unverified": "NEEDS CLARIFICATION"}


def build_pdf(kind: str, title: str, report: AuditReport, appeal: str | None) -> bytes:
    pdf = _PDF(title, report.demo)
    pdf.add_page()
    if kind == "appeal":
        pdf.para(appeal or "")
        return bytes(pdf.output())

    pdf.para(f"Claim audit report: {title}", 14, "B")
    pdf.para(f"Method: {report.method}, rules {report.rules_version}. Generated {report.generated_at}.", 8)
    pdf.ln(2)
    for label, v in [("Hospital bill (sum of lines)", report.bill_total), ("Amount claimed", report.claimed_amount),
                     ("Amount approved", report.approved_amount), ("Amount paid", report.paid_amount),
                     ("Total deductions", report.total_deductions),
                     ("Supported by documents", report.supported_total),
                     ("Potentially contestable", report.contestable_total),
                     ("Needs clarification", report.unverified_total)]:
        pdf.set_font("Helvetica", "", 9.5)
        pdf.cell(80, 5.5, label)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.cell(0, 5.5, _latin1(rs(v) if v is not None or label != "Amount paid" else "not stated"),
                 new_x="LMARGIN", new_y="NEXT")
    if report.readiness:
        pdf.ln(2)
        pdf.para(f"Appeal readiness: {report.readiness.summary}", 9, "I")
    pdf.ln(3)
    pdf.para("Findings", 12, "B")
    for f in report.findings:
        pdf.ln(1)
        pdf.para(f"{f.id}. {f.description}  [{STATUS_WORDS[f.status]}]", 10, "B")
        pdf.para(f"Rule {f.rule_id} ({f.rule_title}). Deducted {rs(f.insurer_amount)}; supported "
                 f"{rs(f.supported_amount)}; contestable {rs(f.contestable_amount)}.", 9)
        pdf.para(f"Insurer stated: {f.insurer_statement}", 9)
        if f.policy_clause:
            pdf.para(f"Policy clause applied: {f.policy_clause}", 9)
        pdf.para(f.explanation, 9)
        if f.contestable_reason:
            pdf.para(f"Why it may be contestable: {f.contestable_reason}", 9)
        if f.basis_label:
            pdf.para(f"Basis: {f.basis_label}.", 8.5, "I")
        for step in f.calculation:
            pdf.para(f"  - {step}", 8.5)
        for e in f.evidence:
            pdf.para(f"  Evidence ({ref(e)}{'' if e.found else ', NOT FOUND'}): {e.excerpt[:300]}", 8)
        if f.missing:
            pdf.para("  Missing: " + "; ".join(f.missing), 8.5)
        pdf.para(f"  Next step: {f.next_step}", 8.5)
    if report.checks:
        pdf.ln(2)
        pdf.para("Consistency checks", 12, "B")
        for c in report.checks:
            pdf.para(f"{c.id} {c.title}: {c.status.replace('_', ' ').upper()}. {c.detail}", 8.5)
    if report.documents_to_request:
        pdf.ln(2)
        pdf.para("Documents and clarifications to request", 12, "B")
        for m in report.documents_to_request:
            pdf.para(f"- {m}", 9)
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
