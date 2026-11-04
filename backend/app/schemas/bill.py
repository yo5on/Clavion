"""Hospital bill extraction schema, plus arithmetic checks done in Python (never trusted to the model)."""

import re
from decimal import Decimal

from pydantic import BaseModel, field_validator

TOLERANCE = Decimal("0.01")


def _money(v):
    if isinstance(v, str):
        v = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", v)
        return v or None
    return v


class BillLineItem(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal

    _clean = field_validator("quantity", "unit_price", "amount", mode="before")(_money)


class HospitalBill(BaseModel):
    hospital_name: str | None = None
    bill_number: str | None = None
    patient_name: str | None = None
    bill_date: str | None = None  # as printed on the bill
    line_items: list[BillLineItem]
    total_amount: Decimal | None = None

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


EXTRACTION_INSTRUCTIONS = """Extract the hospital bill into JSON with exactly these keys:
{"hospital_name": str|null, "bill_number": str|null, "patient_name": str|null, "bill_date": str|null,
 "line_items": [{"description": str, "quantity": number|null, "unit_price": number|null, "amount": number}],
 "total_amount": number|null}
Copy values exactly as printed. Use null for anything not present. Do not compute or correct amounts.
Return only the JSON object."""
