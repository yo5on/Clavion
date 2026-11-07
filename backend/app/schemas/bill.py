"""Hospital bill extraction schema, plus arithmetic checks done in Python."""

import re
from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, Field, field_validator

TOLERANCE = Decimal("0.01")
NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


def _money(v):
    if isinstance(v, str):
        v = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", v)
        return v or None
    return v


class BillLineItem(BaseModel):
    description: str
    quantity: Positive | None = None
    unit_price: NonNegative | None = None
    amount: NonNegative
    category: str | None = None  # set by the local parser or manual correction; see services/parsers.categorize

    _clean = field_validator("quantity", "unit_price", "amount", mode="before")(_money)


class HospitalBill(BaseModel):
    hospital_name: str | None = None
    bill_number: str | None = None
    patient_name: str | None = None
    bill_date: str | None = None  # as printed on the bill
    admission_date: str | None = None  # as printed
    discharge_date: str | None = None  # as printed
    line_items: list[BillLineItem]
    total_amount: NonNegative | None = None

    _clean = field_validator("total_amount", mode="before")(_money)

    def arithmetic_issues(self) -> list[str]:
        issues = []
        for i, it in enumerate(self.line_items, 1):
            if it.quantity is not None and it.unit_price is not None:
                expected = it.quantity * it.unit_price
                if abs(expected - it.amount) > TOLERANCE:
                    issues.append(f"line {i} '{it.description}': {it.quantity} x {it.unit_price} = {expected}, bill says {it.amount}")
        items_sum = sum((it.amount for it in self.line_items), Decimal(0))
        if self.total_amount is None:
            issues.append("total amount missing")
        elif abs(items_sum - self.total_amount) > TOLERANCE:
            issues.append(f"line items sum to {items_sum}, total says {self.total_amount}")
        return issues
