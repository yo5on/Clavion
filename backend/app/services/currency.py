"""The one place amounts become text: Indian digit grouping (12,34,567.89), paise kept, Decimal only."""

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def rs(v: Decimal | int | str | None) -> str:
    """₹1,30,940.50 for Decimal('130940.5'); '-' when the amount is missing. Rounds half up to the paisa."""
    if v is None:
        return "-"
    q = Decimal(v).quantize(PAISE, ROUND_HALF_UP)
    whole, paise = f"{abs(q):f}".split(".")
    head, groups = whole[:-3], [whole[-3:]]
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"{'-' if q < 0 else ''}₹{','.join(groups)}.{paise}"
