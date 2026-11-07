"""Explainable audit rules.

Deduction rules (R-*) assess one deduction on the settlement letter. Each has an id, the inputs it needs, the
condition under which a deduction is supported, and an evaluate function that records every condition it checked
(met / not met / could not be checked), the evidence it rests on (with page and line) and what is missing.

Consistency checks (C-*) compare the documents with each other. Each reports passed, failed or not_checked, and
not_checked always says which input was missing, so a check that did not run is never read as one that passed.

All money arithmetic is Decimal, in services/calculations.py. No rule calls a model or an external service.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from ..schemas.bill import HospitalBill
from ..schemas.claim import (Check, Condition, Evidence, FieldMeta, PolicyDocument, SettlementDeduction,
                             SettlementLetter)
from . import calculations as calc
from .currency import rs
from .parsers import CATEGORY_LABELS, categorize, parse_date
from .policy_analysis import token_overlap, tokens

# Words insurers use to state a reason; they say nothing about which bill item a deduction is for.
REASON_WORDS = {"non", "payable", "nonpayable", "excluded", "exclusion", "inadmissible", "deduction", "deducted",
                "disallowed", "admissible", "medical", "being", "treated"}

RULES_VERSION = "2026.11-1"
ZERO = Decimal("0.00")
# Differences up to this much between the insurer's figure and the recalculation are treated as rounding, not as a
# contestable amount: insurers round ratios and intermediate figures differently.
ROUNDING_TOLERANCE = Decimal("1.00")

# What a finding's conclusion rests on. Shown with every finding so a reader can weigh it.
BASIS = {
    "recalculated": "Recalculated from the bill and policy figures",
    "policy_list": "Bill lines matched against the policy's list of items",
    "clause_absent": "No policy wording for this deduction was found in the uploaded policy",
    "insufficient": "The uploaded documents do not contain enough information to decide",
    "no_reason": "The insurer gave no reason or calculation",
    "reconciliation": "Settlement letter arithmetic (claimed - approved - listed deductions)",
}
ANNEX_REF = re.compile(r"\b(Annexure|Appendix|Schedule|List)\s*[-–]?\s*([IVX]+|\d+|[A-Z])\b")


def cat(item) -> str:
    return item.category or categorize(item.description)


# ---------------------------------------------------------------- context shared by all rules

class Ctx:
    def __init__(self, bill: HospitalBill | None, policy: PolicyDocument | None, settlement: SettlementLetter,
                 sources: dict[str, dict[str, FieldMeta]] | None = None, filenames: dict[str, str] | None = None):
        self.bill, self.policy, self.settlement = bill, policy, settlement
        self.sources, self.filenames = sources or {}, filenames or {}
        self.missing: list[str] = []  # report-wide
        self.requests: list[str] = []  # documents or clarifications to ask for, report-wide
        self.reset()

    def reset(self):
        """Per-deduction scratch state."""
        self.basis: str | None = None
        self.conditions: list[Condition] = []
        self.local_missing: list[str] = []
        self.targets: list[int] = []  # bill lines the deduction is about (not just context)

    # -- bookkeeping
    def note(self, msg: str):
        if msg not in self.missing:
            self.missing.append(msg)

    def lack(self, msg: str, request: str | None = None, report: bool = True):
        """Something this deduction needs that the documents do not show."""
        if msg not in self.local_missing:
            self.local_missing.append(msg)
        if report:
            self.note(msg)
        if request and request not in self.requests:
            self.requests.append(request)

    def cond(self, text: str, met: bool | None) -> bool | None:
        self.conditions.append(Condition(text=text, met=met))
        return met

    # -- evidence with source locations
    def _src(self, doc_type: str, path: str):
        m = self.sources.get(doc_type, {}).get(path)
        return m.source if m else None

    def ev(self, doc_type: str, ref: str, excerpt: str, path: str | None = None, found: bool = True) -> Evidence:
        return Evidence(doc_type=doc_type, ref=ref, excerpt=excerpt, found=found,
                        document=self.filenames.get(doc_type), source=self._src(doc_type, path) if path else None)

    def clause_ev(self, clause_id: str | None) -> list[Evidence]:
        p = self.policy
        c = p.clause(clause_id) if p else None
        if not c:
            return []
        i = p.clauses.index(c)
        return [self.ev("policy", f"Clause {c.id}", c.text, f"clauses.{i}")]

    def bill_ev(self, items) -> list[Evidence]:
        return [self.ev("bill", f"Bill line {n}", f"{it.description}: {rs(it.amount)}", f"line_items.{n - 1}")
                for n, it in items]

    def items(self, pred) -> list:
        return [(n, it) for n, it in enumerate(self.bill.line_items, 1) if pred(it)] if self.bill else []

    def clause_name(self, clause_id: str | None) -> str | None:
        c = self.policy.clause(clause_id) if self.policy and clause_id else None
        return f"Clause {c.id} ({c.title})" if c else (f"Clause {clause_id}" if clause_id else None)


@dataclass
class Outcome:
    supported: Decimal | None  # amount the documents support deducting; None = cannot be decided
    why: str
    steps: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    clause: str | None = None  # policy clause id the rule applied
    contest_reason: str | None = None  # specific reason the insurer's figure differs, when it can be shown


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    kind: str  # deduction type this rule assesses
    pattern: str  # wording on the settlement letter that selects this rule
    requires: tuple[str, ...]  # inputs the rule needs
    supported_when: str  # the rule's condition, in words
    evaluate: Callable[[Ctx, SettlementDeduction], Outcome]


def _no_policy(ctx: Ctx, what: str) -> Outcome:
    ctx.cond("Policy wording uploaded", False)
    ctx.lack("Policy not provided: deductions cannot be checked against policy clauses", "The full policy wording",
             report=False)
    return Outcome(None, f"The policy wording was not provided, so the {what} cannot be checked.")


# ---------------------------------------------------------------- R-ROOM-01 / R-ICU-01: per-day limits

def _daily_limit(ctx: Ctx, d: SettlementDeduction, category: str) -> Outcome:
    p = ctx.policy
    name = CATEGORY_LABELS[category]
    lname = name.lower() if category != "icu" else "ICU charges"
    if not p:
        return _no_policy(ctx, f"{lname} limit")
    limit, clause = (p.room_rent_limit_per_day, p.room_rent_clause) if category == "room_rent" else \
        (p.icu_limit_per_day, p.icu_clause)
    if not ctx.cond(f"Policy states a {lname} limit per day", limit is not None):
        if category == "room_rent" and p.room_rent_category:
            ctx.lack(f"Clause {clause} limits the room category ({p.room_rent_category}), not an amount per day",
                     f"The insurer's eligible room rent per day for a {p.room_rent_category}, and how it was set")
            return Outcome(None, f"Clause {clause} limits the room to a {p.room_rent_category} rather than an amount "
                                 f"per day, so the eligible rent cannot be worked out from the policy alone.",
                           evidence=ctx.clause_ev(clause), clause=clause)
        ctx.lack(f"{name} limit per day not found in the policy", f"The policy clause setting the {lname} limit")
        return Outcome(None, f"The uploaded policy does not state a {lname} limit per day, so this deduction cannot "
                             f"be checked.")
    items = ctx.items(lambda it: cat(it) == category)
    ctx.targets = [n for n, _ in items]
    if not ctx.cond(f"Bill shows {lname} lines with days", bool(items) and all(
            it.quantity is not None and it.quantity > 0 for _, it in items)):
        ctx.lack(f"{name} days or daily rate not found on the bill",
                 f"An itemised bill showing {lname} days and the daily rate")
        return Outcome(None, f"The bill does not show {lname} days and daily rate.", evidence=ctx.clause_ev(clause),
                       clause=clause)
    supported, steps = ZERO, [f"Policy limit {rs(limit)}/day (Clause {clause})"]
    for n, it in items:
        rate = it.unit_price if it.unit_price is not None else calc.q(it.amount / it.quantity)
        excess = calc.excess_over_daily_limit(rate, limit, it.quantity)
        supported += excess
        steps.append(f"Bill line {n}: {it.quantity} day(s) at {rs(rate)}; excess = (max({rs(rate)} - {rs(limit)}, 0))"
                     f" x {it.quantity} = {rs(excess)}")
    supported = calc.q(supported)
    if len(items) > 1:
        steps.append(f"Total excess = {rs(supported)}")
    ctx.cond(f"Charged rate exceeds the {rs(limit)}/day limit", supported > 0)
    why = f"Clause {clause} limits {lname} to {rs(limit)} per day. Recalculated line by line from the bill, " \
          f"{rs(supported)} is above the limit."
    reason = None
    if supported == 0:
        reason = f"Every {lname} line on the bill is within the {rs(limit)}/day limit, so Clause {clause} supports " \
                 f"no deduction."
    elif d.amount > supported:
        reason = f"The recalculated excess over the {rs(limit)}/day limit is {rs(supported)}; the insurer deducted " \
                 f"{rs(d.amount)}."
    return Outcome(supported, why, steps, ctx.clause_ev(clause) + ctx.bill_ev(items), clause, reason)


# ---------------------------------------------------------------- R-PROP-01: proportionate deduction

def _proportionate(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    p = ctx.policy
    if not p:
        return _no_policy(ctx, "proportionate deduction")
    if not ctx.cond("Policy has a proportionate-deduction clause", bool(p.proportionate_clause)):
        ctx.basis = "clause_absent"
        return Outcome(ZERO, "No proportionate-deduction clause was found in the uploaded policy, so the documents do "
                             "not support this deduction. Confirm the policy wording is complete.",
                       contest_reason="No clause in the uploaded policy provides for a proportionate deduction.")
    clause = p.proportionate_clause
    room_items = ctx.items(lambda it: cat(it) == "room_rent")
    limit = p.room_rent_limit_per_day
    rates = {(it.unit_price if it.unit_price is not None else calc.q(it.amount / it.quantity))
             for _, it in room_items if it.quantity}
    if not ctx.cond("Policy states a room-rent limit per day", limit is not None):
        ctx.lack("Room-rent rate or policy limit missing: proportionate deduction cannot be recalculated",
                 "The insurer's eligible room rent per day and the ratio applied")
        return Outcome(None, "The policy's room-rent limit per day is not known, so the proportion cannot be "
                             "recalculated.", evidence=ctx.clause_ev(clause), clause=clause)
    if not ctx.cond("Bill shows the room rent per day", bool(room_items) and len(rates) >= 1 and all(
            it.quantity for _, it in room_items)):
        ctx.lack("Room-rent rate or policy limit missing: proportionate deduction cannot be recalculated",
                 "An itemised bill showing room days and the daily room rent")
        return Outcome(None, "The bill does not show the room rent per day, so the proportion cannot be recalculated.",
                       evidence=ctx.clause_ev(clause), clause=clause)
    if not ctx.cond("Bill shows a single room rate (one room category)", len(rates) == 1):
        ctx.lack("Bill shows more than one room rate: the proportion the insurer applied cannot be recalculated",
                 "The insurer's calculation of the proportionate deduction (room rate and ratio used)")
        return Outcome(None, f"The bill shows more than one room rate ({', '.join(rs(r) for r in sorted(rates))}), so "
                             f"it is not clear which rate the proportion should use.",
                       evidence=ctx.clause_ev(clause) + ctx.bill_ev(room_items), clause=clause)
    rate = rates.pop()
    excluded = {"room_rent", "icu", "admin", *p.proportionate_exclusions}
    assoc = ctx.items(lambda it: cat(it) not in excluded)
    ctx.targets = [n for n, _ in assoc]
    base = calc.bill_total(it.amount for _, it in assoc)
    reason = None
    if not ctx.cond(f"Room rent {rs(rate)}/day exceeds the {rs(limit)}/day limit", rate > limit):
        supported, steps = ZERO, [f"Room rent {rs(rate)}/day is within the {rs(limit)}/day limit"]
        reason = f"The room rent ({rs(rate)}/day) is within the policy limit ({rs(limit)}/day), so Clause {clause} " \
                 f"does not apply."
    else:
        r = calc.room_rent_proportionate_deduction(limit, rate, base)
        supported = r["deduction"]
        steps = [f"Ratio = eligible / actual room rent = {rs(limit)} / {rs(rate)} = {r['ratio']}",
                 f"Associated charges (bill lines {', '.join(str(n) for n, _ in assoc) or 'none'}) = {rs(base)}",
                 f"Payable = {rs(base)} x ratio = {rs(r['payable'])}; deduction = {rs(supported)}"]
        if d.amount > supported + ROUNDING_TOLERANCE:
            # What base would the insurer's figure imply? If it equals the associated charges plus the excluded
            # categories, say so: that is arithmetic, not a guess about the insurer's method.
            implied = calc.q(d.amount / (1 - limit / rate))
            steps.append(f"The insurer's {rs(d.amount)} implies {rs(implied)} of charges were proportioned "
                         f"({rs(d.amount)} / (1 - {rs(limit)} / {rs(rate)}))")
            # Which exempt categories, added to the base, reproduce the insurer's figure? Checked exactly for every
            # combination (a policy exempts at most a handful of categories).
            present = sorted({cat(it) for _, it in ctx.items(lambda it: cat(it) in set(p.proportionate_exclusions))})
            match = None
            for mask in range(1, 2 ** len(present)):
                cats = [c for i, c in enumerate(present) if mask >> i & 1]
                extra = ctx.items(lambda it: cat(it) in cats)
                candidate = calc.room_rent_proportionate_deduction(
                    limit, rate, base + calc.bill_total(it.amount for _, it in extra))["deduction"]
                if abs(candidate - d.amount) <= ROUNDING_TOLERANCE:
                    match = (cats, extra, candidate)
                    break
            if match:
                cats, extra, candidate = match
                names = " and ".join(CATEGORY_LABELS.get(c, c).lower() for c in cats)
                steps.append(f"Adding {names} (bill lines {', '.join(str(n) for n, _ in extra)}) to the associated "
                             f"charges gives a deduction of {rs(candidate)}, the insurer's figure")
                reason = f"The insurer's figure is reproduced exactly by also proportioning {names} (bill lines " \
                         f"{', '.join(str(n) for n, _ in extra)}). Clause {clause} says the proportionate deduction " \
                         f"does not apply to {names}."
            else:
                reason = f"Recalculated on the charges Clause {clause} covers, the deduction is {rs(supported)}; the " \
                         f"insurer's figure implies {rs(implied)} of charges were proportioned, against {rs(base)}."
    steps.append("Not treated as associated charges: room rent and ICU (they have their own limits) and "
                 "administrative charges")
    if p.proportionate_exclusions:
        steps.append("Not proportioned per Clause %s: %s" % (
            clause, ", ".join(CATEGORY_LABELS.get(c, c) for c in p.proportionate_exclusions)))
    why = f"Clause {clause} allows associated charges to be reduced in proportion to the eligible room rent. " \
          f"Recalculated on the charges the clause covers, the deduction is {rs(supported)}."
    return Outcome(supported, why, steps, ctx.clause_ev(clause) + ctx.bill_ev(assoc + room_items), clause, reason)


# ---------------------------------------------------------------- R-NONPAY-01 / R-EXCL-01: listed items

def _non_payable(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    p = ctx.policy
    return _listed(ctx, d, p.non_payable_items if p else [], p.non_payable_clause if p else None, "non-payable")


def _exclusion(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    p = ctx.policy
    return _listed(ctx, d, p.exclusions if p else [], p.exclusions_clause if p else None, "excluded")


def _listed(ctx: Ctx, d: SettlementDeduction, policy_items: list[str], clause: str | None, noun: str) -> Outcome:
    """A deduction for items the policy lists (non-payable items, or permanent exclusions): supported only for bill
    lines whose item is on that list."""
    p = ctx.policy
    # A bill line matches if most of its words are in the deduction, or every meaningful word of the deduction
    # (ignoring the insurer's reason words) is in the line: "Excluded - Hearing aid" matches "Hearing aid".
    core = set(tokens(d.description)) - REASON_WORDS
    matched = ctx.items(lambda it: token_overlap(it.description, d.description) >= 0.6
                        or (bool(core) and core <= set(tokens(it.description))))
    ctx.targets = [n for n, _ in matched]
    if not p:
        o = _no_policy(ctx, f"{noun} list")
        o.evidence = ctx.bill_ev(matched)
        return o
    if not ctx.cond(f"Policy lists {noun} items", bool(policy_items)):
        ctx.lack(f"No list of {noun} items found in the policy", f"The policy's list of {noun} items")
        return Outcome(None, f"The uploaded policy has no list of {noun} items to check this against.",
                       evidence=ctx.bill_ev(matched))

    def listed(desc: str) -> list[str]:
        return [x for x in policy_items if token_overlap(x, desc) == 1.0]

    ev = ctx.clause_ev(clause) + ctx.bill_ev(matched)
    if not ctx.cond("The deducted item matches a bill line", bool(matched)):
        # Never take the insurer's amount on trust: without a bill line the amount itself cannot be checked.
        hits = listed(d.description)
        ctx.lack(f"No bill line found for '{d.description}'", report=False)
        if hits:
            ctx.cond(f"Item is on the Clause {clause} list", True)
            return Outcome(None, f"Clause {clause} lists {', '.join(hits)} as {noun}, but no bill line for this "
                                 f"item was found, so the amount deducted cannot be checked against the bill.",
                           evidence=ev, clause=clause)
        return Outcome(None, f"The deducted item could not be matched to a bill line or the policy's {noun} list.",
                       evidence=ev, clause=clause)
    ctx.basis = "policy_list"
    supported, steps, unlisted = ZERO, [], []
    for n, it in matched:
        hits = listed(it.description)
        if hits:
            supported += it.amount
            steps.append(f"Bill line {n} '{it.description}' ({rs(it.amount)}) matches listed: {', '.join(hits)}")
            ctx.cond(f"Bill line {n} '{it.description}' is on the Clause {clause} list", True)
        else:
            unlisted.append(it.description)
            steps.append(f"Bill line {n} '{it.description}' ({rs(it.amount)}) is not on the {noun} list")
            ctx.cond(f"Bill line {n} '{it.description}' is on the Clause {clause} list", False)
    supported = min(supported, d.amount)
    c = p.clause(clause)
    external = [" ".join(m) for m in ANNEX_REF.findall(c.text if c else "")
                if not any(x.id.lower().startswith(m[0].lower()) for x in p.clauses)]
    if unlisted and external:
        ctx.lack(f"Non-payable list refers to {', '.join(external)}, which is not in the uploaded policy",
                 f"{', '.join(external)} of the policy (the full list of {noun} items)")
        return Outcome(None, f"Clause {clause} refers to {', '.join(external)} for its list of {noun} items, "
                             f"which is not in the uploaded policy. Whether {', '.join(unlisted)} is on that list "
                             f"cannot be checked until it is provided.", steps, ev, clause)
    reason = None
    if unlisted:
        ctx.basis = "clause_absent"
        why = f"Clause {clause} lists the policy's {noun} items; {', '.join(unlisted)} is not among them, so the " \
              f"uploaded policy does not support deducting it. Check that the policy does not incorporate a further " \
              f"list" + (" (for example the IRDAI standard list of non-payable items)" if noun == "non-payable" else "") \
            + " by reference."
        reason = f"{', '.join(unlisted)} is not on Clause {clause}'s list of {noun} items."
    else:
        why = f"Clause {clause} lists these items as {noun}."
    return Outcome(supported, why, steps, ev, clause, reason)


# ---------------------------------------------------------------- R-SUBLIMIT-01

def _sublimit(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    p = ctx.policy
    if not p:
        return _no_policy(ctx, "sub-limit")
    if not ctx.cond("Policy states sub-limits", bool(p.sub_limits)):
        ctx.lack("No sub-limits found in the policy", "The policy clause setting the sub-limit applied")
        return Outcome(None, "No sub-limits were found in the uploaded policy to check this against.")
    lines = ctx.bill.line_items if ctx.bill else []

    def score(s) -> float:  # match on the deduction's wording first, then on any single bill line
        return max([token_overlap(s.name, d.description)] + [token_overlap(s.name, it.description) for it in lines])
    best = max(p.sub_limits, key=score)
    if not ctx.cond(f"A policy sub-limit matches this treatment (best: {best.name})", score(best) >= 0.5):
        ctx.basis = "clause_absent"
        return Outcome(ZERO, "None of the policy's sub-limits matches the treatment on this claim.",
                       evidence=ctx.clause_ev(p.sub_limits[0].clause_id),
                       contest_reason="None of the sub-limits in the uploaded policy matches the treatment billed.")
    items = ctx.items(lambda it: token_overlap(best.name, it.description) >= 0.5)
    ctx.targets = [n for n, _ in items]
    ev = ctx.clause_ev(best.clause_id) + ctx.bill_ev(items)
    if not ctx.cond(f"Bill shows charges for {best.name}", bool(items)):
        ctx.lack(f"No bill line found for {best.name}", f"An itemised bill showing the {best.name} charges")
        return Outcome(None, f"The policy caps {best.name} at {rs(best.limit)}, but no matching bill line was found.",
                       evidence=ev, clause=best.clause_id)
    billed = calc.bill_total(it.amount for _, it in items)
    supported = calc.sublimit_deduction(billed, best.limit)
    ctx.cond(f"Billed {rs(billed)} exceeds the {rs(best.limit)} sub-limit", billed > best.limit)
    steps = [f"Billed for {best.name} = {rs(billed)}; sub-limit {rs(best.limit)} (Clause {best.clause_id})",
             f"Excess over sub-limit = {rs(supported)}"]
    reason = f"Billed {rs(billed)} less the {rs(best.limit)} sub-limit leaves {rs(supported)} deductible; the " \
             f"insurer deducted {rs(d.amount)}." if d.amount > supported else None
    return Outcome(supported, f"Clause {best.clause_id} caps {best.name} at {rs(best.limit)}.", steps, ev,
                   best.clause_id, reason)


# ---------------------------------------------------------------- R-COPAY-01

def _copay(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    p = ctx.policy
    if not p:
        return _no_policy(ctx, "co-payment")
    if not ctx.cond("Policy states a co-payment percentage", p.copay_percent is not None):
        ctx.basis = "clause_absent"
        return Outcome(ZERO, "No co-payment clause was found in the uploaded policy.",
                       contest_reason="No clause in the uploaded policy provides for a co-payment.")
    clause, pct = p.copay_clause, p.copay_percent
    claimed = ctx.settlement.claimed_amount
    if not ctx.cond("Settlement letter states the claimed amount", claimed is not None):
        ctx.lack("Claimed amount missing, so the co-payment cannot be recalculated", "The claimed amount")
        return Outcome(None, "Claimed amount missing, so the co-payment cannot be recalculated.",
                       evidence=ctx.clause_ev(clause), clause=clause)
    from .audit import classify_deduction  # deferred: audit imports this module

    others = [x.amount for x in ctx.settlement.deductions if classify_deduction(x.description) != "copay"]
    admissible = calc.q(claimed - sum(others, ZERO))
    supported = calc.copay_amount(admissible, pct)
    steps = [f"Admissible amount = claimed {rs(claimed)} - other deductions {rs(sum(others, ZERO))} = "
             f"{rs(admissible)}", f"Co-pay = {pct}% x {rs(admissible)} = {rs(supported)}"]
    why = f"Clause {clause} sets a {pct}% co-payment, applied to the admissible amount (the claim after the other " \
          f"deductions)."
    reason = None
    if d.amount > supported + ROUNDING_TOLERANCE:
        on_claim = calc.copay_amount(claimed, pct)
        reason = f"{pct}% of the full claimed amount {rs(claimed)} is {rs(on_claim)}" + (
            ", which is what the insurer deducted: the co-payment appears to have been applied before the other "
            "deductions instead of to the admissible amount." if abs(on_claim - d.amount) <= ROUNDING_TOLERANCE
            else f"; on the admissible amount it is {rs(supported)}.")
    if p.copay_condition:
        ctx.cond(f"Co-payment condition met ({p.copay_condition})", None)
        ctx.lack(f"Co-payment condition must be checked: applies {p.copay_condition}",
                 f"Proof that the co-payment condition applies ({p.copay_condition})")
        return Outcome(None, why + f" It applies only {p.copay_condition}; the documents do not show whether this "
                                   f"condition is met. If met, up to {rs(supported)} is deductible.", steps,
                       ctx.clause_ev(clause), clause)
    return Outcome(supported, why, steps, ctx.clause_ev(clause), clause, reason)


# ---------------------------------------------------------------- R-UNSPEC-01

def _unspecified(ctx: Ctx, d: SettlementDeduction) -> Outcome:
    ctx.basis = "no_reason"
    ctx.cond("Letter states a reason or a clause for the deduction", bool(d.clause_ref))
    ctx.lack("The insurer's reason, clause and calculation for this deduction", report=False)
    if f"The clause and calculation for '{d.description}'" not in ctx.requests:
        ctx.requests.append(f"The clause and calculation for '{d.description}'")
    return Outcome(None, "The letter gives no specific reason for this deduction. Ask the insurer for the exact "
                         "clause and calculation.")


RULES: list[Rule] = [
    Rule("R-PROP-01", "Proportionate deduction", "proportionate", r"proportion",
         ("policy.proportionate_clause", "policy.room_rent_limit_per_day", "bill room-rent lines with days"),
         "Associated charges (excluding categories the policy exempts) x (1 - eligible / actual room rent)",
         _proportionate),
    Rule("R-ICU-01", "ICU charges above limit", "icu_excess", r"\bicu\b|intensive",
         ("policy.icu_limit_per_day", "bill ICU lines with days"),
         "Sum over ICU lines of max(rate - limit, 0) x days", lambda c, d: _daily_limit(c, d, "icu")),
    Rule("R-ROOM-01", "Room rent above limit", "room_rent_excess", r"room\s*(?:rent|charge)",
         ("policy.room_rent_limit_per_day", "bill room-rent lines with days"),
         "Sum over room-rent lines of max(rate - limit, 0) x days", lambda c, d: _daily_limit(c, d, "room_rent")),
    Rule("R-COPAY-01", "Co-payment", "copay", r"co-?\s*pay",
         ("policy.copay_percent", "settlement.claimed_amount"),
         "Co-pay % x (claimed - other deductions), if the policy's condition (if any) is met", _copay),
    Rule("R-SUBLIMIT-01", "Sub-limit", "sublimit", r"sub-?\s*limit|\bcapped\b",
         ("policy.sub_limits", "bill lines for the treatment"), "max(billed for the treatment - sub-limit, 0)",
         _sublimit),
    Rule("R-EXCL-01", "Policy exclusion", "exclusion", r"\bexclu(?:ded|sion)",
         ("policy.exclusions", "bill lines for the item"),
         "Bill lines whose treatment or item is on the policy's list of exclusions", _exclusion),
    Rule("R-NONPAY-01", "Non-payable items", "non_payable",
         r"non-?\s*payable|not\s+payable|non-?\s*medical|consumable|inadmissible",
         ("policy.non_payable_items", "bill lines for the item"),
         "Bill lines whose item is on the policy's list of non-payable items", _non_payable),
    Rule("R-UNSPEC-01", "Unspecified reason", "unspecified", r"$^", (), "The letter must state the reason", _unspecified),
]
RULES_BY_KIND = {r.kind: r for r in RULES}
KIND_LABELS = {r.kind: r.title for r in RULES} | {"unexplained": "Unexplained difference"}
# Policy fields that hold the clause behind each deduction type, used to classify vaguely worded deductions.
RULE_CLAUSE_FIELDS = {"room_rent_excess": "room_rent_clause", "icu_excess": "icu_clause",
                      "proportionate": "proportionate_clause", "copay": "copay_clause",
                      "non_payable": "non_payable_clause", "exclusion": "exclusions_clause"}


# ---------------------------------------------------------------- consistency checks (C-*)

def _names_match(a: str, b: str) -> bool:
    return token_overlap(a, b) >= 0.6 or token_overlap(b, a) >= 0.6


def run_checks(ctx: Ctx, findings, doc_info: dict[str, dict]) -> list[Check]:
    b, p, s = ctx.bill, ctx.policy, ctx.settlement
    out: list[Check] = []

    def add(id_, title, status, detail, requires=(), evidence=()):
        out.append(Check(id=id_, title=title, status=status, detail=detail, requires=list(requires),
                         evidence=list(evidence)))

    ded_sum = calc.bill_total(d.amount for d in s.deductions)
    if s.claimed_amount is None or s.approved_amount is None:
        add("C-REC-01", "Settlement letter adds up", "not_checked",
            "The claimed or approved amount is missing from the settlement letter.",
            ["settlement.claimed_amount", "settlement.approved_amount"])
    else:
        gap = calc.reconciliation_gap(s.claimed_amount, s.approved_amount, [d.amount for d in s.deductions])
        add("C-REC-01", "Settlement letter adds up", "passed" if gap == 0 else "failed",
            f"Claimed {rs(s.claimed_amount)} - approved {rs(s.approved_amount)} = {rs(s.claimed_amount - s.approved_amount)}"
            f"; listed deductions add up to {rs(ded_sum)}" + ("." if gap == 0 else f"; difference {rs(abs(gap))}."))
    if s.total_deductions is None:
        add("C-REC-02", "Stated total deductions matches the items", "not_checked",
            "The letter does not state a total for its deductions.", ["settlement.total_deductions"])
    else:
        add("C-REC-02", "Stated total deductions matches the items",
            "passed" if s.total_deductions == ded_sum else "failed",
            f"Stated {rs(s.total_deductions)}; items add up to {rs(ded_sum)}.")
    if not b:
        for id_, t in (("C-REC-03", "Bill lines add up to the bill total"),
                       ("C-REC-04", "Quantity x rate = amount on every bill line"),
                       ("C-REC-05", "Claimed amount equals the bill total"),
                       ("C-DUP-01", "No duplicate bill lines"), ("C-STAY-01", "Room days within the length of stay")):
            add(id_, t, "not_checked", "Hospital bill not provided.", ["bill"])
    else:
        items_total = calc.bill_total(it.amount for it in b.line_items)
        if b.total_amount is None:
            add("C-REC-03", "Bill lines add up to the bill total", "not_checked",
                "The bill's printed total was not found.", ["bill.total_amount"])
        else:
            add("C-REC-03", "Bill lines add up to the bill total",
                "passed" if abs(items_total - b.total_amount) <= Decimal("0.01") else "failed",
                f"Lines add up to {rs(items_total)}; the bill states {rs(b.total_amount)}.")
        bad = [f"line {i}: {it.quantity} x {rs(it.unit_price)} = {rs(calc.q(it.quantity * it.unit_price))}, "
               f"billed {rs(it.amount)}" for i, it in enumerate(b.line_items, 1)
               if it.quantity is not None and it.unit_price is not None
               and abs(it.quantity * it.unit_price - it.amount) > Decimal("0.01")]
        with_rate = sum(1 for it in b.line_items if it.quantity is not None and it.unit_price is not None)
        add("C-REC-04", "Quantity x rate = amount on every bill line",
            "not_checked" if not with_rate else ("failed" if bad else "passed"),
            "No bill line shows both quantity and rate." if not with_rate else
            ("; ".join(bad) if bad else f"All {with_rate} lines with a quantity and rate multiply out."),
            ["bill line quantities and rates"])
        if s.claimed_amount is None:
            add("C-REC-05", "Claimed amount equals the bill total", "not_checked", "Claimed amount missing.",
                ["settlement.claimed_amount"])
        else:
            add("C-REC-05", "Claimed amount equals the bill total",
                "passed" if items_total == s.claimed_amount else "failed",
                f"Bill lines total {rs(items_total)}; claimed {rs(s.claimed_amount)}." + (
                    "" if items_total == s.claimed_amount else " A difference can be legitimate (pre-authorised or "
                                                               "partial claims) but should be explained."))
        seen, dups = {}, []
        for i, it in enumerate(b.line_items, 1):
            key = (it.description.strip().lower(), it.amount)
            if key in seen:
                dups.append((seen[key], i, it))
            else:
                seen[key] = i
        add("C-DUP-01", "No duplicate bill lines", "failed" if dups else "passed",
            "; ".join(f"lines {a} and {c} are both '{it.description}' for {rs(it.amount)}" for a, c, it in dups)
            + (". This may be double billing, or two genuine charges: ask the hospital." if dups else "")
            or f"No two of the {len(b.line_items)} lines share a description and amount.",
            evidence=[ctx.ev("bill", f"Bill line {n}", f"{it.description}: {rs(it.amount)}", f"line_items.{n - 1}")
                      for a, c, it in dups for n in (a, c)])
        adm, dis = parse_date(b.admission_date), parse_date(b.discharge_date)
        stay_items = ctx.items(lambda it: cat(it) in ("room_rent", "icu"))
        days = sum((it.quantity for _, it in stay_items if it.quantity), Decimal(0))
        if not (adm and dis):
            add("C-STAY-01", "Room days within the length of stay", "not_checked",
                "Admission or discharge date not found on the bill.", ["bill.admission_date", "bill.discharge_date"])
        elif not days:
            add("C-STAY-01", "Room days within the length of stay", "not_checked",
                "The bill does not show room or ICU days.", ["bill room-rent lines with days"])
        else:
            stay = (dis - adm).days
            # Hospitals count either nights or calendar days, so one extra day is normal.
            add("C-STAY-01", "Room days within the length of stay", "passed" if days <= stay + 1 else "failed",
                f"Admitted {adm:%d %b %Y}, discharged {dis:%d %b %Y}: {stay} night(s). Room and ICU days billed: "
                f"{days}." + ("" if days <= stay + 1 else " More days are billed than the stay allows; ask the "
                                                          "hospital to explain."),
                evidence=ctx.bill_ev(stay_items))
    keys = [(d.description.strip().lower(), d.amount) for d in s.deductions]
    dup_ded = [i for i, k in enumerate(keys, 1) if k in keys[:i - 1]]
    add("C-DUP-02", "No duplicate deductions", "failed" if dup_ded else "passed",
        f"Deduction(s) {', '.join(map(str, dup_ded))} repeat an earlier deduction with the same wording and amount."
        if dup_ded else f"No two of the {len(s.deductions)} deductions share wording and amount.")
    # Deductions against the same bill lines must not take more than was billed for them.
    groups: dict[tuple, list] = {}
    for f, targets in findings:
        if targets and f.category in ("Non-payable items", "Policy exclusion", "Sub-limit", "Room rent above limit",
                                      "ICU charges above limit"):
            groups.setdefault(tuple(sorted(targets)), []).append(f)
    over = []
    for targets, fs in groups.items():
        billed = calc.bill_total(b.line_items[n - 1].amount for n in targets) if b else ZERO
        taken = calc.bill_total(f.insurer_amount for f in fs)
        if taken > billed:
            over.append(f"deduction(s) {', '.join(str(f.id) for f in fs)} take {rs(taken)} from bill line(s) "
                        f"{', '.join(map(str, targets))}, which were billed {rs(billed)}")
    add("C-OVL-01", "Deductions do not exceed what was billed", "not_checked" if not b else (
        "failed" if over else "passed"),
        "Hospital bill not provided." if not b else ("; ".join(over) + "." if over else
                                                     "No item is deducted for more than its billed amount."))
    cited = [(i, d.clause_ref) for i, d in enumerate(s.deductions, 1) if d.clause_ref]
    if not p:
        add("C-CIT-01", "Every clause the insurer cites is in the policy", "not_checked", "Policy not provided.",
            ["policy"])
    elif not cited:
        add("C-CIT-01", "Every clause the insurer cites is in the policy", "not_checked",
            "The settlement letter cites no clauses.")
    else:
        absent = [(i, c) for i, c in cited if not p.clause(c)]
        add("C-CIT-01", "Every clause the insurer cites is in the policy", "failed" if absent else "passed",
            "; ".join(f"Clause {c} (deduction {i}) is not in the uploaded policy" for i, c in absent)
            + (". The upload may be incomplete." if absent else "")
            or f"All {len(cited)} cited clauses were found.")
    if p and s.policy_number and p.policy_number:
        add("C-ID-01", "Policy number matches", "passed" if p.policy_number == s.policy_number else "failed",
            f"Letter: {s.policy_number}; policy: {p.policy_number}.")
    else:
        add("C-ID-01", "Policy number matches", "not_checked", "Policy number missing from the letter or the policy.",
            ["settlement.policy_number", "policy.policy_number"])
    for id_, title, a, c in (("C-ID-02", "Patient name matches", b and b.patient_name, s.patient_name),
                             ("C-ID-03", "Hospital matches", b and b.hospital_name, s.hospital_name)):
        if a and c:
            add(id_, title, "passed" if _names_match(a, c) else "failed", f"Bill: {a}; letter: {c}.")
        else:
            add(id_, title, "not_checked", "Missing from the bill or the settlement letter.")
    if s.paid_amount is None or s.approved_amount is None:
        add("C-REC-06", "Amount paid equals amount approved", "not_checked",
            "The letter does not state the amount paid separately.", ["settlement.paid_amount"])
    else:
        add("C-REC-06", "Amount paid equals amount approved",
            "passed" if s.paid_amount == s.approved_amount else "failed",
            f"Approved {rs(s.approved_amount)}; paid {rs(s.paid_amount)}." + (
                "" if s.paid_amount == s.approved_amount else " Ask the insurer to explain the difference."))
    if p and p.sum_insured is not None and s.approved_amount is not None:
        add("C-SI-01", "Approved amount within the sum insured",
            "passed" if s.approved_amount <= p.sum_insured else "failed",
            f"Approved {rs(s.approved_amount)}; sum insured {rs(p.sum_insured)}.")
    warned = [f"{t}: {len(i['warnings'])} warning(s)" for t, i in doc_info.items()
              if i.get("warnings") and not i.get("manually_corrected")]
    add("C-DOC-01", "Documents read without unreviewed extraction warnings",
        "not_checked" if not doc_info else ("failed" if warned else "passed"),
        "; ".join(warned) + ". Check those fields on the review screen and save corrections." if warned else
        ("Extraction details not available." if not doc_info else "No extraction warnings, or the documents were "
                                                                   "corrected after review."))
    return out
