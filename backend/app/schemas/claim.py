"""Settlement letter, policy and audit report schemas. Monetary values are Decimal throughout."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from .bill import NonNegative, _money

DocType = Literal["bill", "policy", "settlement"]
FindingStatus = Literal["supported", "contestable", "unverified"]
FindingBasis = Literal["recalculated", "policy_list", "clause_absent", "insufficient", "no_reason", "reconciliation"]
FieldStatus = Literal["extracted", "inferred", "missing", "corrected"]


class SourceRef(BaseModel):
    """Where a value was read: page (1-based), line within the page (1-based, blank lines counted) and that line."""

    page: int
    line: int
    text: str


class FieldMeta(BaseModel):
    status: FieldStatus
    source: SourceRef | None = None
    note: str | None = None  # how an inferred value was derived, or why a value is missing


class Provenance(BaseModel):
    """Where a piece of data came from. The UI shows this next to every extracted document and report."""

    provider: Literal["local", "demo"]
    label: str
    ai_generated: bool = False  # always False: Clavion runs no AI models
    demo: bool = False  # demo fixture or synthetic test document
    manually_corrected: bool = False
    text_method: str | None = None  # pdf-text, pdf-ocr, image-ocr, plain-text
    pages: int = 1
    sha256: str | None = None  # of the uploaded file; used to detect the same file uploaded twice
    warnings: list[str] = []


class SettlementDeduction(BaseModel):
    description: str
    amount: NonNegative
    clause_ref: str | None = None  # clause number the insurer cited, e.g. "4.3"

    _clean = field_validator("amount", mode="before")(_money)


class SettlementLetter(BaseModel):
    insurer_name: str | None = None
    claim_number: str | None = None
    policy_number: str | None = None
    patient_name: str | None = None
    hospital_name: str | None = None
    claimed_amount: NonNegative | None = None
    approved_amount: NonNegative | None = None
    paid_amount: NonNegative | None = None  # amount actually transferred, when the letter states it
    total_deductions: NonNegative | None = None
    deductions: list[SettlementDeduction] = []

    _clean = field_validator("claimed_amount", "approved_amount", "paid_amount", "total_deductions",
                             mode="before")(_money)


class PolicyClause(BaseModel):
    id: str  # clause number as printed, e.g. "4.3", or "preamble"
    title: str
    text: str


class SubLimit(BaseModel):
    name: str
    limit: NonNegative
    clause_id: str | None = None

    _clean = field_validator("limit", mode="before")(_money)


class PolicyDocument(BaseModel):
    policy_name: str | None = None
    policy_number: str | None = None
    sum_insured: NonNegative | None = None
    room_rent_limit_per_day: NonNegative | None = None
    room_rent_clause: str | None = None
    room_rent_category: str | None = None  # e.g. "single private room": a category limit with no rupee amount
    icu_limit_per_day: NonNegative | None = None
    icu_clause: str | None = None
    proportionate_clause: str | None = None
    proportionate_exclusions: list[str] = []  # bill categories the proportionate deduction does not apply to
    copay_percent: Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)] | None = None
    copay_condition: str | None = None
    copay_clause: str | None = None
    non_payable_items: list[str] = []
    non_payable_clause: str | None = None
    exclusions: list[str] = []  # treatments or items the policy excludes outright
    exclusions_clause: str | None = None
    sub_limits: list[SubLimit] = []
    clauses: list[PolicyClause] = []

    _clean = field_validator("sum_insured", "room_rent_limit_per_day", "icu_limit_per_day", "copay_percent",
                             mode="before")(_money)

    def clause(self, clause_id: str | None) -> PolicyClause | None:
        return next((c for c in self.clauses if c.id == clause_id), None) if clause_id else None


class Evidence(BaseModel):
    doc_type: DocType
    ref: str  # "Clause 4.3", "Bill line 2", "Deduction 1"
    excerpt: str
    found: bool = True  # False: the reference was cited but is not in the uploaded document
    document: str | None = None  # uploaded file name
    source: SourceRef | None = None  # page and line in that file, when known


class Condition(BaseModel):
    """One condition a rule checked. met=None: it could not be checked with the documents provided."""

    text: str
    met: bool | None


class Finding(BaseModel):
    id: int
    rule_id: str = ""
    rule_title: str = ""
    description: str
    category: str
    insurer_amount: Decimal
    status: FindingStatus
    basis: FindingBasis = "recalculated"  # what the conclusion rests on; see services/rules.BASIS
    basis_label: str = ""
    supported_amount: Decimal | None  # what the uploaded documents support deducting; None = cannot tell
    contestable_amount: Decimal
    # The eight questions every finding answers
    what_happened: str = ""
    insurer_statement: str = ""
    policy_clause: str | None = None  # the clause the rule applied, e.g. "Clause 4.3 Proportionate Deduction"
    explanation: str  # the analysis: why the amount is or is not supported
    contestable_reason: str | None = None  # only for contestable findings
    missing: list[str] = []
    next_step: str = ""
    classification: str = ""  # why this rule was chosen for the deduction
    conditions: list[Condition] = []
    calculation: list[str] = []
    evidence: list[Evidence] = []
    related_clauses: list[str] = []


class Check(BaseModel):
    """A cross-document consistency check. not_checked says which input was missing, so a check that did not
    trigger is never mistaken for one that passed."""

    id: str
    title: str
    status: Literal["passed", "failed", "not_checked"]
    detail: str
    requires: list[str] = []
    evidence: list[Evidence] = []


class ReadinessItem(BaseModel):
    label: str
    ok: bool
    detail: str = ""


class Readiness(BaseModel):
    """Whether the documents support writing to the insurer now. Counts verifiable checks; it is not a score of
    how likely an appeal is to succeed."""

    state: Literal["ready", "needs_information", "nothing_to_appeal"]
    summary: str
    items: list[ReadinessItem]


class BreakdownRow(BaseModel):
    category: str
    amount: Decimal
    count: int


class AuditReport(BaseModel):
    method: str
    rules_version: str = ""
    demo: bool
    generated_at: str
    bill_total: Decimal | None
    bill_stated_total: Decimal | None
    claimed_amount: Decimal | None
    approved_amount: Decimal | None
    paid_amount: Decimal | None = None
    total_deductions: Decimal
    supported_total: Decimal
    contestable_total: Decimal
    unverified_total: Decimal
    breakdown: list[BreakdownRow]
    findings: list[Finding]
    checks: list[Check] = []
    readiness: Readiness | None = None
    documents_to_request: list[str] = []
    missing_information: list[str]


StatementKind = Literal["source_fact", "calculation", "suggestion", "standard"]


class AppealStatement(BaseModel):
    """One statement of the appeal letter. kind tells the reader what it rests on:
    source_fact  taken from an uploaded document (refs say where)
    calculation  Clavion's recalculation from those documents
    suggestion   generated wording (an argument or a request) the policyholder should review
    standard     letter formalities (address, salutation, closing)"""

    id: str
    section: str
    kind: StatementKind
    text: str = Field(max_length=5000)
    refs: list[str] = []
    include: bool = True
    edited: bool = False
    finding_id: int | None = None
