"""Claim audit engine. Deterministic: every amount comes from services/calculations.py, every conclusion cites the
uploaded document it rests on, and anything the documents cannot support is marked unverified."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from ..schemas.bill import HospitalBill
from ..schemas.claim import (AuditReport, BreakdownRow, Evidence, Finding, PolicyDocument, SettlementDeduction,
                             SettlementLetter)
from . import calculations as calc
from .parsers import CATEGORY_LABELS, categorize
from .policy_analysis import search_clauses, token_overlap

METHOD = "Local deterministic rules (no AI inference)"
ZERO = Decimal("0.00")

DEDUCTION_KINDS = [
    ("proportionate", "Proportionate deduction", r"proportion"),
    ("icu_excess", "ICU charges above limit", r"\bicu\b|intensive"),
    ("room_rent_excess", "Room rent above limit", r"room\s*(?:rent|charge)"),
    ("copay", "Co-payment", r"co-?\s*pay"),
    ("sublimit", "Sub-limit", r"sub-?\s*limit|\bcapped\b"),
    ("non_payable", "Non-payable items", r"non-?\s*payable|not\s+payable|non-?\s*medical|consumable|inadmissible"),
]
KIND_LABELS = {k: label for k, label, _ in DEDUCTION_KINDS} | {"unspecified": "Unspecified reason",
                                                               "unexplained": "Unexplained difference"}


def classify_deduction(description: str) -> str:
    return next((k for k, _, pat in DEDUCTION_KINDS if re.search(pat, description, re.I)), "unspecified")


def _cat(item) -> str:
    return item.category or categorize(item.description)


def _money(v: Decimal) -> str:
    return f"Rs {v:,.2f}"


class _Ctx:
    def __init__(self, bill: HospitalBill | None, policy: PolicyDocument | None, settlement: SettlementLetter):
        self.bill, self.policy, self.settlement = bill, policy, settlement
        self.missing: list[str] = []

    def note(self, msg: str):
        if msg not in self.missing:
            self.missing.append(msg)

    def clause_ev(self, clause_id: str | None) -> list[Evidence]:
        c = self.policy.clause(clause_id) if self.policy else None
        return [Evidence(doc_type="policy", ref=f"Clause {c.id}", excerpt=c.text)] if c else []

    def bill_ev(self, items) -> list[Evidence]:
        return [Evidence(doc_type="bill", ref=f"Bill line {n}", excerpt=f"{it.description}: {_money(it.amount)}")
                for n, it in items]

    def items(self, pred) -> list:
        return [(n, it) for n, it in enumerate(self.bill.line_items, 1) if pred(it)] if self.bill else []

    def stay(self, category: str):
        """(items, rate per day, days) for room or ICU lines; rate/days None when the bill lacks quantities."""
        items = self.items(lambda it: _cat(it) == category)
        if not items or any(it.quantity is None or it.quantity <= 0 for _, it in items):
            return items, None, None
        days = sum(it.quantity for _, it in items)
        return items, calc.q(sum(it.amount for _, it in items) / days), days


def _daily_limit(ctx: _Ctx, d: SettlementDeduction, category: str):
    p = ctx.policy
    limit, clause = (p.room_rent_limit_per_day, p.room_rent_clause) if category == "room_rent" and p else \
        (p.icu_limit_per_day, p.icu_clause) if p else (None, None)
    name = CATEGORY_LABELS[category]
    if limit is None:
        if p:
            ctx.note(f"{name} limit per day not found in the policy")
        return None, f"The uploaded policy does not state a {name.lower()} limit per day, so this deduction cannot "\
                     f"be checked.", [], []
    items, rate, days = ctx.stay(category)
    if rate is None:
        ctx.note(f"{name} days or daily rate not found on the bill")
        return None, f"The bill does not show {name.lower()} days and daily rate.", [], ctx.clause_ev(clause)
    supported = calc.excess_over_daily_limit(rate, limit, days)
    steps = [f"Charged {_money(rate)}/day for {days} day(s); policy limit {_money(limit)}/day (Clause {clause})",
             f"Excess = ({_money(rate)} - {_money(limit)}) x {days} = {_money(supported)}"]
    why = f"Clause {clause} limits {name.lower()} to {_money(limit)} per day. The bill charges {_money(rate)} per " \
          f"day for {days} day(s), so up to {_money(supported)} is deductible."
    return supported, why, steps, ctx.clause_ev(clause) + ctx.bill_ev(items)


def _proportionate(ctx: _Ctx, d: SettlementDeduction):
    p = ctx.policy
    if not p:
        return None, "Policy not provided.", [], []
    if not p.proportionate_clause:
        return ZERO, "No proportionate-deduction clause was found in the uploaded policy, so the documents do not "\
                     "support this deduction. Confirm the policy wording is complete.", [], []
    room_items, rate, days = ctx.stay("room_rent")
    limit = p.room_rent_limit_per_day
    if rate is None or limit is None:
        ctx.note("Room-rent rate or policy limit missing: proportionate deduction cannot be recalculated")
        return None, "Room-rent rate or policy limit is missing, so the proportion cannot be recalculated.", [], \
            ctx.clause_ev(p.proportionate_clause)
    excluded = {"room_rent", "icu", "admin", *p.proportionate_exclusions}
    assoc = ctx.items(lambda it: _cat(it) not in excluded)
    base = calc.bill_total(it.amount for _, it in assoc)
    if rate <= limit:
        supported, steps = ZERO, [f"Room rent {_money(rate)}/day is within the {_money(limit)}/day limit"]
    else:
        r = calc.room_rent_proportionate_deduction(limit, rate, base)
        supported = r["deduction"]
        steps = [f"Ratio = eligible / actual room rent = {_money(limit)} / {_money(rate)} = {r['ratio']}",
                 f"Associated charges (bill lines {', '.join(str(n) for n, _ in assoc)}) = {_money(base)}",
                 f"Payable = {_money(base)} x ratio = {_money(r['payable'])}; deduction = {_money(supported)}"]
    if p.proportionate_exclusions:
        steps.append("Not proportioned per Clause %s: %s" % (
            p.proportionate_clause, ", ".join(CATEGORY_LABELS.get(c, c) for c in p.proportionate_exclusions)))
    why = f"Clause {p.proportionate_clause} allows associated charges to be reduced in proportion to the eligible "\
          f"room rent. Recalculated on the charges the clause covers, the deduction is {_money(supported)}."
    return supported, why, steps, ctx.clause_ev(p.proportionate_clause) + ctx.bill_ev(assoc + room_items)


def _non_payable(ctx: _Ctx, d: SettlementDeduction):
    p = ctx.policy
    matched = ctx.items(lambda it: token_overlap(it.description, d.description) >= 0.6)
    if not p:
        return None, "Policy not provided.", [], ctx.bill_ev(matched)
    if not p.non_payable_items:
        ctx.note("No list of non-payable items found in the policy")
        return None, "The uploaded policy has no list of non-payable items to check this against.", [], \
            ctx.bill_ev(matched)

    def listed(desc: str) -> list[str]:
        return [x for x in p.non_payable_items if token_overlap(x, desc) == 1.0]

    ev = ctx.clause_ev(p.non_payable_clause) + ctx.bill_ev(matched)
    if not matched:
        hits = listed(d.description)
        if hits:
            return d.amount, f"Clause {p.non_payable_clause} lists {', '.join(hits)} as non-payable.", [], ev
        return None, "The deducted item could not be matched to a bill line or the policy's non-payable list.", [], ev
    supported, steps, unlisted = ZERO, [], []
    for n, it in matched:
        hits = listed(it.description)
        if hits:
            supported += it.amount
            steps.append(f"Bill line {n} '{it.description}' ({_money(it.amount)}) matches listed: {', '.join(hits)}")
        else:
            unlisted.append(it.description)
            steps.append(f"Bill line {n} '{it.description}' ({_money(it.amount)}) is not on the non-payable list")
    supported = min(supported, d.amount)
    if unlisted:
        why = f"Clause {p.non_payable_clause} lists the policy's non-payable items; {', '.join(unlisted)} " \
              f"is not among them, so the uploaded policy does not support deducting it."
    else:
        why = f"Clause {p.non_payable_clause} lists these items as non-payable."
    return supported, why, steps, ev


def _sublimit(ctx: _Ctx, d: SettlementDeduction):
    p = ctx.policy
    if not p:
        return None, "Policy not provided.", [], []
    if not p.sub_limits:
        ctx.note("No sub-limits found in the policy")
        return None, "No sub-limits were found in the uploaded policy to check this against.", [], []
    scored = sorted(((token_overlap(s.name, d.description + " " + " ".join(
        it.description for it in (ctx.bill.line_items if ctx.bill else []))), s) for s in p.sub_limits),
                    key=lambda x: -x[0])
    if scored[0][0] < 0.5:
        return ZERO, "None of the policy's sub-limits matches the treatment on this claim.", [], \
            ctx.clause_ev(p.sub_limits[0].clause_id)
    sl = scored[0][1]
    items = ctx.items(lambda it: token_overlap(sl.name, it.description) >= 0.5)
    ev = ctx.clause_ev(sl.clause_id) + ctx.bill_ev(items)
    if not items:
        return None, f"The policy caps {sl.name} at {_money(sl.limit)}, but no matching bill line was found.", [], ev
    billed = calc.bill_total(it.amount for _, it in items)
    supported = calc.sublimit_deduction(billed, sl.limit)
    steps = [f"Billed for {sl.name} = {_money(billed)}; sub-limit {_money(sl.limit)} (Clause {sl.clause_id})",
             f"Excess over sub-limit = {_money(supported)}"]
    return supported, f"Clause {sl.clause_id} caps {sl.name} at {_money(sl.limit)}.", steps, ev


def _copay(ctx: _Ctx, d: SettlementDeduction):
    p = ctx.policy
    if not p:
        return None, "Policy not provided.", [], []
    if p.copay_percent is None:
        return ZERO, "No co-payment clause was found in the uploaded policy.", [], []
    claimed = ctx.settlement.claimed_amount
    if claimed is None:
        return None, "Claimed amount missing, so the co-payment cannot be recalculated.", [], ctx.clause_ev(p.copay_clause)
    others = [x.amount for x in ctx.settlement.deductions if classify_deduction(x.description) != "copay"]
    admissible = calc.q(claimed - sum(others, ZERO))
    supported = calc.copay_amount(admissible, p.copay_percent)
    steps = [f"Admissible amount = claimed {_money(claimed)} - other deductions {_money(sum(others, ZERO))} = "
             f"{_money(admissible)}", f"Co-pay = {p.copay_percent}% x {_money(admissible)} = {_money(supported)}"]
    why = f"Clause {p.copay_clause} sets a {p.copay_percent}% co-payment."
    if p.copay_condition:
        ctx.note(f"Co-payment condition must be checked: applies {p.copay_condition}")
        return None, why + f" It applies only {p.copay_condition}; the documents do not show whether this " \
                           f"condition is met. If met, up to {_money(supported)} is deductible.", steps, \
            ctx.clause_ev(p.copay_clause)
    return supported, why, steps, ctx.clause_ev(p.copay_clause)


def _unspecified(ctx: _Ctx, d: SettlementDeduction):
    return None, "The letter gives no specific reason for this deduction. Ask the insurer for the exact clause "\
                 "and calculation.", [], []


HANDLERS = {"room_rent_excess": lambda c, d: _daily_limit(c, d, "room_rent"),
            "icu_excess": lambda c, d: _daily_limit(c, d, "icu"), "proportionate": _proportionate,
            "non_payable": _non_payable, "sublimit": _sublimit, "copay": _copay, "unspecified": _unspecified}


def _assess(ctx: _Ctx, n: int, d: SettlementDeduction) -> Finding:
    kind = classify_deduction(d.description)
    supported, why, steps, evidence = HANDLERS[kind](ctx, d)
    evidence = [Evidence(doc_type="settlement", ref=f"Deduction {n}", excerpt=f"{d.description}: {_money(d.amount)}")] \
        + evidence
    if d.clause_ref and ctx.policy:
        if not (cited := ctx.policy.clause(d.clause_ref)):
            evidence.append(Evidence(doc_type="policy", ref=f"Clause {d.clause_ref}", found=False,
                                     excerpt="Cited by the insurer but not found in the uploaded policy."))
            ctx.note(f"Clause {d.clause_ref} cited in deduction {n} is not in the uploaded policy")
        elif all(e.ref != f"Clause {cited.id}" for e in evidence):
            evidence.append(Evidence(doc_type="policy", ref=f"Clause {cited.id}", excerpt=cited.text))
    related = [c.id for c, _ in search_clauses(ctx.policy.clauses, d.description)] if ctx.policy else []

    if supported is None:
        status, cont = "unverified", ZERO
    else:
        cont = calc.contestable(d.amount, supported)
        status = "contestable" if cont > 0 else "supported"
        if cont > 0:
            why += f" The insurer deducted {_money(d.amount)}, {_money(cont)} more than the documents support."
        elif supported > d.amount:
            why += f" The insurer deducted less than this ({_money(d.amount)})."
    return Finding(id=n, description=d.description, category=KIND_LABELS[kind], insurer_amount=d.amount,
                   status=status, supported_amount=supported, contestable_amount=cont, explanation=why,
                   calculation=steps, evidence=evidence, related_clauses=related)


def run_audit(bill: HospitalBill | None, policy: PolicyDocument | None, settlement: SettlementLetter | None,
              demo: bool = False) -> AuditReport:
    ctx = _Ctx(bill, policy, settlement or SettlementLetter())
    s = ctx.settlement
    if not bill:
        ctx.note("Hospital bill not provided: bill lines and room-rent figures cannot be checked")
    if not policy:
        ctx.note("Policy not provided: deductions cannot be checked against policy clauses")
    if not settlement:
        ctx.note("Settlement letter not provided: there are no deductions to audit")

    findings = [_assess(ctx, n, d) for n, d in enumerate(s.deductions, 1)]
    total_ded = calc.bill_total(d.amount for d in s.deductions)

    if s.claimed_amount is not None and s.approved_amount is not None:
        gap = calc.reconciliation_gap(s.claimed_amount, s.approved_amount, [d.amount for d in s.deductions])
        if gap > 0:
            findings.append(Finding(
                id=len(findings) + 1, description="Reduction not explained by any listed deduction",
                category=KIND_LABELS["unexplained"], insurer_amount=gap, status="unverified", supported_amount=None,
                contestable_amount=ZERO, calculation=[
                    f"Claimed {_money(s.claimed_amount)} - approved {_money(s.approved_amount)} - listed deductions "
                    f"{_money(total_ded)} = {_money(gap)}"],
                explanation="The settlement letter reduces the claim by more than its itemised deductions. Ask the "
                            "insurer to itemise the remaining amount.",
                evidence=[Evidence(doc_type="settlement", ref="Settlement summary",
                                   excerpt=f"Claimed {_money(s.claimed_amount)}, approved {_money(s.approved_amount)}")]))
            total_ded = calc.q(total_ded + gap)
        elif gap < 0:
            ctx.note(f"Listed deductions exceed claimed minus approved by {_money(-gap)}")
    else:
        ctx.note("Claimed or approved amount missing from the settlement letter")
    if s.total_deductions is not None and s.total_deductions != calc.bill_total(d.amount for d in s.deductions):
        ctx.note(f"Letter states total deductions {_money(s.total_deductions)}, but its items add up to "
                 f"{_money(calc.bill_total(d.amount for d in s.deductions))}")
    if bill:
        ctx.missing.extend(f"Bill arithmetic: {i}" for i in bill.arithmetic_issues())
    if bill and s.claimed_amount is not None and bill.line_items:
        items_total = calc.bill_total(it.amount for it in bill.line_items)
        if items_total != s.claimed_amount:
            ctx.note(f"Bill lines total {_money(items_total)} but the claim is for {_money(s.claimed_amount)}")
    if policy and s.policy_number and policy.policy_number and policy.policy_number != s.policy_number:
        ctx.note(f"Policy number on the letter ({s.policy_number}) differs from the policy ({policy.policy_number})")

    rows: dict[str, BreakdownRow] = {}
    for f in findings:
        r = rows.setdefault(f.category, BreakdownRow(category=f.category, amount=ZERO, count=0))
        r.amount, r.count = calc.q(r.amount + f.insurer_amount), r.count + 1

    contestable = calc.bill_total(f.contestable_amount for f in findings)
    unverified = calc.bill_total(f.insurer_amount for f in findings if f.status == "unverified")
    return AuditReport(
        method=METHOD, demo=demo, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        bill_total=calc.bill_total(it.amount for it in bill.line_items) if bill else None,
        bill_stated_total=bill.total_amount if bill else None,
        claimed_amount=s.claimed_amount, approved_amount=s.approved_amount, total_deductions=total_ded,
        supported_total=calc.q(total_ded - contestable - unverified), contestable_total=contestable,
        unverified_total=unverified, breakdown=list(rows.values()), findings=findings,
        missing_information=ctx.missing)
