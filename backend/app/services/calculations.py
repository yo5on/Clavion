"""Deterministic money calculations. The model may choose to call these; it never does the arithmetic itself."""

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
