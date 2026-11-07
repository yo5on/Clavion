"""Claim audit engine. Deterministic: every amount comes from services/calculations.py, every conclusion cites the
uploaded document it rests on, and anything the documents cannot support is marked unverified.

Each deduction is assigned one rule from services/rules.py (by its wording, or by the clause it cites when the
wording gives no reason). The rule's outcome becomes a Finding that answers: what happened, what amount, what the
insurer stated, which clause applies, what evidence supports it, why it may be contestable, what is missing and
what to do next. Cross-document consistency checks run afterwards.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal

from ..schemas.bill import HospitalBill
from ..schemas.claim import (AuditReport, BreakdownRow, Condition, Evidence, FieldMeta, Finding, PolicyDocument,
                             Readiness, ReadinessItem, SettlementDeduction, SettlementLetter)
from . import calculations as calc
from .policy_analysis import search_clauses
from .rules import (BASIS, KIND_LABELS, ROUNDING_TOLERANCE, RULE_CLAUSE_FIELDS, RULES, RULES_BY_KIND, RULES_VERSION,
                    Ctx, rs, run_checks)

METHOD = "Local deterministic rules (no AI inference)"
ZERO = Decimal("0.00")


def classify_deduction(description: str) -> str:
    return next((r.kind for r in RULES if re.search(r.pattern, description, re.I)), "unspecified")


def _kind(ctx: Ctx, d: SettlementDeduction) -> tuple[str, str]:
    """Deduction type from its wording; if the wording gives no reason, from the policy clause it cites."""
    kind = classify_deduction(d.description)
    if kind != "unspecified":
        rule = RULES_BY_KIND[kind]
        m = re.search(rule.pattern, d.description, re.I)
        return kind, f"Rule {rule.id} chosen because the deduction's wording mentions '{m.group(0)}'"
    if d.clause_ref and ctx.policy:
        p = ctx.policy
        note = f"The letter gives no reason; the deduction type is taken from the clause it cites (Clause {d.clause_ref})"
        for k, fld in RULE_CLAUSE_FIELDS.items():
            if getattr(p, fld) == d.clause_ref:
                return k, note
        if any(sl.clause_id == d.clause_ref for sl in p.sub_limits):
            return "sublimit", note
    return kind, "No deduction type could be identified from the wording" + (
        f" or from Clause {d.clause_ref}" if d.clause_ref else "")


def _assess(ctx: Ctx, n: int, d: SettlementDeduction) -> tuple[Finding, list[int]]:
    ctx.reset()
    kind, classification = _kind(ctx, d)
    rule = RULES_BY_KIND[kind]
    o = rule.evaluate(ctx, d)
    supported, why, steps, evidence = o.supported, o.why, list(o.steps), list(o.evidence)
    if classification.startswith("The letter gives no reason"):
        steps = [classification] + steps
    evidence = [ctx.ev("settlement", f"Deduction {n}", f"{d.description}: {rs(d.amount)}", f"deductions.{n - 1}")] \
        + evidence
    rule_clause = next((e.ref for e in evidence if e.doc_type == "policy" and e.found), None)
    if d.clause_ref and ctx.policy:
        if not (cited := ctx.policy.clause(d.clause_ref)):
            evidence.append(Evidence(doc_type="policy", ref=f"Clause {d.clause_ref}", found=False,
                                     document=ctx.filenames.get("policy"),
                                     excerpt="Cited by the insurer but not found in the uploaded policy."))
            ctx.lack(f"Clause {d.clause_ref} cited in deduction {n} is not in the uploaded policy",
                     f"The text of Clause {d.clause_ref} (cited by the insurer)")
            ctx.cond(f"Clause {d.clause_ref} cited by the insurer is in the uploaded policy", False)
            if ctx.basis == "clause_absent" and supported is not None and supported < d.amount:
                # The conclusion rests on the policy lacking a rule, yet the insurer cites wording we do not have:
                # the upload may be incomplete, so the deduction is not called contestable.
                why += f" However, the insurer cites Clause {d.clause_ref}, which is not in the uploaded policy. " \
                       f"The uploaded wording may be incomplete: ask the insurer for the text of Clause " \
                       f"{d.clause_ref} before contesting this deduction."
                supported, ctx.basis = None, "insufficient"
        else:
            if all(e.ref != f"Clause {cited.id}" for e in evidence):
                evidence += ctx.clause_ev(cited.id)
            if rule_clause and rule_clause != f"Clause {cited.id}":
                why += f" Note: the insurer cites Clause {cited.id} ({cited.title}), but the policy rule applied " \
                       f"here is in {rule_clause}."
                ctx.note(f"Deduction {n} cites Clause {cited.id}, which does not match the policy's "
                         f"{KIND_LABELS[kind].lower()} rule ({rule_clause})")
                ctx.cond(f"Cited Clause {cited.id} is the clause the rule applies", False)
    related = [c.id for c, _ in search_clauses(ctx.policy.clauses, d.description)] if ctx.policy else []

    reason = None
    if supported is None:
        status, cont = "unverified", ZERO
        basis = ctx.basis if ctx.basis in ("no_reason", "insufficient") else "insufficient"
    else:
        cont = calc.contestable(d.amount, supported)
        basis = ctx.basis or "recalculated"
        if 0 < cont <= ROUNDING_TOLERANCE:
            why += f" The insurer's figure differs from the recalculation by {rs(cont)}, which is within rounding " \
                   f"(up to {rs(ROUNDING_TOLERANCE)}) and is not treated as contestable."
            steps.append(f"Difference {rs(d.amount)} - {rs(supported)} = {rs(cont)}: treated as rounding")
            cont = ZERO
        status = "contestable" if cont > 0 else "supported"
        if cont > 0:
            why += f" The insurer deducted {rs(d.amount)}, {rs(cont)} more than the documents support."
            reason = o.contest_reason or f"The documents support {rs(supported)}; the insurer deducted {rs(d.amount)}."
            if basis == "clause_absent":
                reason += " This rests on the uploaded policy not containing wording that supports the deduction: " \
                          "confirm the policy document is complete before relying on it."
        elif supported > d.amount:
            why += f" The insurer deducted less than this ({rs(d.amount)})."

    policy_clause = ctx.clause_name(o.clause)
    if status == "contestable":
        next_step = f"Ask the insurer to reconsider {rs(cont)}" + (f", quoting {policy_clause}" if policy_clause else "") \
                    + " and the calculation shown."
    elif status == "supported":
        next_step = "No action needed: the uploaded documents support this deduction."
    elif basis == "no_reason":
        next_step = "Write to the insurer asking for the clause and the calculation behind this deduction."
    elif ctx.local_missing:
        next_step = "Obtain the missing information (" + "; ".join(ctx.local_missing) + "), then run the audit again."
    else:
        next_step = "Ask the insurer to explain how this deduction was calculated."
    stated = f"Deduction {n}: \"{d.description}\", {rs(d.amount)}" + (
        f", citing Clause {d.clause_ref}." if d.clause_ref else ", with no clause cited.")
    return Finding(
        id=n, rule_id=rule.id, rule_title=rule.title, description=d.description, category=KIND_LABELS[kind],
        insurer_amount=d.amount, status=status, basis=basis, basis_label=BASIS[basis], supported_amount=supported,
        contestable_amount=cont,
        what_happened=f"The insurer deducted {rs(d.amount)} as \"{d.description}\".",
        insurer_statement=stated, policy_clause=policy_clause, explanation=why, contestable_reason=reason,
        missing=list(ctx.local_missing), next_step=next_step, classification=classification,
        conditions=list(ctx.conditions), calculation=steps, evidence=evidence, related_clauses=related,
    ), list(ctx.targets)


def _readiness(report_docs: dict[str, bool], findings: list[Finding], checks, contestable, unverified) -> Readiness:
    by_id = {c.id: c for c in checks}
    contest = [f for f in findings if f.status == "contestable"]
    items = [
        ReadinessItem(label="Bill, policy and settlement letter uploaded", ok=all(report_docs.values()),
                      detail=", ".join(k for k, v in report_docs.items() if not v) and
                      "Missing: " + ", ".join(k for k, v in report_docs.items() if not v)),
        ReadinessItem(label="Every clause the insurer cites is in the uploaded policy",
                      ok=by_id["C-CIT-01"].status != "failed", detail=by_id["C-CIT-01"].detail),
        ReadinessItem(label="Settlement letter adds up", ok=by_id["C-REC-01"].status == "passed",
                      detail=by_id["C-REC-01"].detail),
        ReadinessItem(label="Contestable amounts rest on policy wording or a recalculation",
                      ok=all(f.basis in ("recalculated", "policy_list") for f in contest),
                      detail="; ".join(f"Finding {f.id} rests on wording missing from the policy" for f in contest
                                       if f.basis not in ("recalculated", "policy_list"))),
        ReadinessItem(label="Extraction warnings reviewed", ok=by_id["C-DOC-01"].status != "failed",
                      detail=by_id["C-DOC-01"].detail),
    ]
    if contestable == 0 and unverified == 0:
        return Readiness(state="nothing_to_appeal", items=items,
                         summary="The uploaded documents support every deduction. There is nothing to contest.")
    ok = sum(i.ok for i in items)
    if contestable > 0 and all(i.ok for i in items[:3]):
        return Readiness(state="ready", items=items,
                         summary=f"{ok} of {len(items)} checks pass. The documents support writing to the insurer "
                                 f"about {rs(contestable)}" + (f" and asking about {rs(unverified)}." if unverified
                                                                else "."))
    return Readiness(state="needs_information", items=items,
                     summary=f"{ok} of {len(items)} checks pass. " + (
                         f"{rs(unverified)} needs an explanation from the insurer; " if unverified else "")
                     + "resolve the open items before relying on the figures.")


def run_audit(bill: HospitalBill | None, policy: PolicyDocument | None, settlement: SettlementLetter | None,
              demo: bool = False, sources: dict[str, dict[str, FieldMeta]] | None = None,
              filenames: dict[str, str] | None = None, doc_info: dict[str, dict] | None = None) -> AuditReport:
    ctx = Ctx(bill, policy, settlement or SettlementLetter(), sources, filenames)
    s = ctx.settlement
    if not bill:
        ctx.note("Hospital bill not provided: bill lines and room-rent figures cannot be checked")
    if not policy:
        ctx.note("Policy not provided: deductions cannot be checked against policy clauses")
        ctx.requests.append("The full policy wording")
    if not settlement:
        ctx.note("Settlement letter not provided: there are no deductions to audit")

    # Co-pay is assessed last: its base uses CLAVION's recalculation of the other deductions, not the insurer's figures.
    results = {}
    for n, d in sorted(enumerate(s.deductions, 1), key=lambda x: _kind(ctx, x[1])[0] == "copay"):
        results[n] = _assess(ctx, n, d)
        ctx.assessed[n] = results[n][0]
    assessed = [results[n] for n in sorted(results)]
    findings = [f for f, _ in assessed]
    total_ded = calc.bill_total(d.amount for d in s.deductions)

    if s.claimed_amount is not None and s.approved_amount is not None:
        gap = calc.reconciliation_gap(s.claimed_amount, s.approved_amount, [d.amount for d in s.deductions])
        if gap > 0:
            findings.append(Finding(
                id=len(findings) + 1, rule_id="R-REC-01", rule_title="Unexplained difference",
                description="Reduction not explained by any listed deduction",
                category=KIND_LABELS["unexplained"], insurer_amount=gap, status="unverified", basis="reconciliation",
                basis_label=BASIS["reconciliation"], supported_amount=None, contestable_amount=ZERO,
                what_happened=f"The claim was reduced by {rs(gap)} more than the itemised deductions explain.",
                insurer_statement=f"Claimed {rs(s.claimed_amount)}, approved {rs(s.approved_amount)}; itemised "
                                  f"deductions {rs(total_ded)}.",
                calculation=[f"Claimed {rs(s.claimed_amount)} - approved {rs(s.approved_amount)} - listed deductions "
                             f"{rs(total_ded)} = {rs(gap)}"],
                conditions=[Condition(text="Claimed - approved = sum of listed deductions", met=False)],
                classification="Rule R-REC-01 runs on every letter that states claimed and approved amounts",
                explanation="The settlement letter reduces the claim by more than its itemised deductions.",
                missing=["An itemised explanation of the remaining reduction"],
                next_step="Ask the insurer to itemise the remaining amount and state the clause behind it.",
                evidence=[ctx.ev("settlement", "Settlement summary",
                                 f"Claimed {rs(s.claimed_amount)}, approved {rs(s.approved_amount)}",
                                 "approved_amount")]))
            ctx.requests.append(f"An itemised explanation of the unexplained {rs(gap)}")
            total_ded = calc.q(total_ded + gap)
        elif gap < 0:
            ctx.note(f"Listed deductions exceed claimed minus approved by {rs(-gap)}")
    else:
        ctx.note("Claimed or approved amount missing from the settlement letter")
    if s.total_deductions is not None and s.total_deductions != calc.bill_total(d.amount for d in s.deductions):
        ctx.note(f"Letter states total deductions {rs(s.total_deductions)}, but its items add up to "
                 f"{rs(calc.bill_total(d.amount for d in s.deductions))}")
    if bill:
        ctx.missing.extend(f"Bill arithmetic: {i}" for i in bill.arithmetic_issues())
    if bill and s.claimed_amount is not None and bill.line_items:
        items_total = calc.bill_total(it.amount for it in bill.line_items)
        if items_total != s.claimed_amount:
            ctx.note(f"Bill lines total {rs(items_total)} but the claim is for {rs(s.claimed_amount)}")
    if policy and s.policy_number and policy.policy_number and policy.policy_number != s.policy_number:
        ctx.note(f"Policy number on the letter ({s.policy_number}) differs from the policy ({policy.policy_number})")

    checks = run_checks(ctx, assessed, doc_info or {})
    for c in checks:  # failed checks not already described above
        if c.status == "failed" and c.id in ("C-DUP-01", "C-DUP-02", "C-OVL-01", "C-STAY-01", "C-ID-02", "C-ID-03",
                                             "C-REC-06", "C-SI-01"):
            ctx.note(f"{c.title}: check failed. {c.detail}")

    rows: dict[str, BreakdownRow] = {}
    for f in findings:
        r = rows.setdefault(f.category, BreakdownRow(category=f.category, amount=ZERO, count=0))
        r.amount, r.count = calc.q(r.amount + f.insurer_amount), r.count + 1

    contestable = calc.bill_total(f.contestable_amount for f in findings)
    unverified = calc.bill_total(f.insurer_amount for f in findings if f.status == "unverified")
    readiness = _readiness({"bill": bill is not None, "policy": policy is not None,
                            "settlement letter": settlement is not None}, findings, checks, contestable, unverified)
    return AuditReport(
        method=METHOD, rules_version=RULES_VERSION, demo=demo,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        bill_total=calc.bill_total(it.amount for it in bill.line_items) if bill else None,
        bill_stated_total=bill.total_amount if bill else None,
        claimed_amount=s.claimed_amount, approved_amount=s.approved_amount, paid_amount=s.paid_amount,
        total_deductions=total_ded, supported_total=calc.q(total_ded - contestable - unverified),
        contestable_total=contestable, unverified_total=unverified, breakdown=list(rows.values()),
        findings=findings, checks=checks, readiness=readiness, documents_to_request=ctx.requests,
        missing_information=ctx.missing)
