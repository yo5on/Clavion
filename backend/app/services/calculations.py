"""Deterministic money calculations. Every amount in an audit comes from these Decimal functions."""

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def room_rent_proportionate_deduction(eligible_room_rent_per_day: Decimal, actual_room_rent_per_day: Decimal,
                                      associated_charges: Decimal) -> dict[str, Decimal]:
    """Proportionate deduction when the room taken costs more than the policy's room-rent limit.

    Associated charges are scaled by eligible/actual. Whether a charge counts as "associated" is policy-specific
    and must be decided from the policy wording, not here.
    """
    eligible, actual, charges = (Decimal(str(v)) for v in (eligible_room_rent_per_day, actual_room_rent_per_day,
                                                            associated_charges))
    if eligible <= 0 or actual <= 0 or charges < 0:
        raise ValueError("room rents must be positive and charges non-negative")
    ratio = min(eligible / actual, Decimal(1))
    payable = (charges * ratio).quantize(PAISE, ROUND_HALF_UP)
    return {"ratio": ratio.quantize(Decimal("0.0001"), ROUND_HALF_UP), "payable": payable,
            "deduction": charges.quantize(PAISE, ROUND_HALF_UP) - payable}


def q(v) -> Decimal:
    return Decimal(str(v)).quantize(PAISE, ROUND_HALF_UP)


def bill_total(amounts) -> Decimal:
    return q(sum((Decimal(str(a)) for a in amounts), Decimal(0)))


def excess_over_daily_limit(actual_per_day, limit_per_day, days) -> Decimal:
    """Amount charged above a per-day limit (room rent, ICU) over the stay."""
    actual, limit, days = (Decimal(str(v)) for v in (actual_per_day, limit_per_day, days))
    if limit <= 0 or days < 0:
        raise ValueError("limit must be positive and days non-negative")
    return q(max(actual - limit, Decimal(0)) * days)


def sublimit_deduction(billed, limit) -> Decimal:
    return q(max(Decimal(str(billed)) - Decimal(str(limit)), Decimal(0)))


def copay_amount(admissible, percent) -> Decimal:
    if not 0 <= Decimal(str(percent)) <= 100:
        raise ValueError("co-pay percent must be between 0 and 100")
    return q(Decimal(str(admissible)) * Decimal(str(percent)) / 100)


def contestable(insurer_deducted, supported) -> Decimal:
    """Part of a deduction the documents do not support. Never negative: under-deduction is not a claim."""
    return q(max(Decimal(str(insurer_deducted)) - Decimal(str(supported)), Decimal(0)))


def reconciliation_gap(claimed, approved, deductions) -> Decimal:
    """claimed - approved - sum(deductions). Non-zero means the letter does not explain every rupee."""
    return q(Decimal(str(claimed)) - Decimal(str(approved)) - sum((Decimal(str(d)) for d in deductions), Decimal(0)))
