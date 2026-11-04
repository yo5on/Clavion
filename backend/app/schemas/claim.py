"""Settlement letter, policy and audit report schemas. Monetary values are Decimal throughout."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator

from .bill import _money

DocType = Literal["bill", "policy", "settlement"]
FindingStatus = Literal["supported", "contestable", "unverified"]


class Provenance(BaseModel):
    """Where a piece of data came from. The UI shows this next to every extracted document and report."""

    provider: Literal["local", "bharatcode", "demo"]
    label: str
    ai_generated: bool = False
    demo: bool = False  # demo fixture or synthetic test document
    manually_corrected: bool = False
    text_method: str | None = None  # pdf-text, pdf-ocr, image-ocr, plain-text
    warnings: list[str] = []


class SettlementDeduction(BaseModel):
    description: str
    amount: Decimal
    clause_ref: str | None = None  # clause number the insurer cited, e.g. "4.3"

    _clean = field_validator("amount", mode="before")(_money)


class SettlementLetter(BaseModel):
    insurer_name: str | None = None
    claim_number: str | None = None
    policy_number: str | None = None
    patient_name: str | None = None
    hospital_name: str | None = None
    claimed_amount: Decimal | None = None
    approved_amount: Decimal | None = None
    total_deductions: Decimal | None = None
    deductions: list[SettlementDeduction] = []

    _clean = field_validator("claimed_amount", "approved_amount", "total_deductions", mode="before")(_money)


class PolicyClause(BaseModel):
    id: str  # clause number as printed, e.g. "4.3", or "preamble"
    title: str
    text: str


class SubLimit(BaseModel):
    name: str
    limit: Decimal
    clause_id: str | None = None

    _clean = field_validator("limit", mode="before")(_money)


class PolicyDocument(BaseModel):
    policy_name: str | None = None
    policy_number: str | None = None
    sum_insured: Decimal | None = None
    room_rent_limit_per_day: Decimal | None = None
    room_rent_clause: str | None = None
    icu_limit_per_day: Decimal | None = None
    icu_clause: str | None = None
    proportionate_clause: str | None = None
    proportionate_exclusions: list[str] = []  # bill categories the proportionate deduction does not apply to
    copay_percent: Decimal | None = None
    copay_condition: str | None = None
    copay_clause: str | None = None
    non_payable_items: list[str] = []
    non_payable_clause: str | None = None
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


class Finding(BaseModel):
    id: int
    description: str
    category: str
    insurer_amount: Decimal
    status: FindingStatus
    supported_amount: Decimal | None  # what the uploaded documents support deducting; None = cannot tell
    contestable_amount: Decimal
    explanation: str
    calculation: list[str] = []
    evidence: list[Evidence] = []
    related_clauses: list[str] = []


class BreakdownRow(BaseModel):
    category: str
    amount: Decimal
    count: int


class AuditReport(BaseModel):
    method: str
    demo: bool
    generated_at: str
    bill_total: Decimal | None
    bill_stated_total: Decimal | None
    claimed_amount: Decimal | None
    approved_amount: Decimal | None
    total_deductions: Decimal
    supported_total: Decimal
    contestable_total: Decimal
    unverified_total: Decimal
    breakdown: list[BreakdownRow]
    findings: list[Finding]
    missing_information: list[str]
