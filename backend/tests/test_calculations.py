from decimal import Decimal

import pytest

from app.services.calculations import room_rent_proportionate_deduction as rr


def test_proportionate_deduction():
    out = rr(5000, 6500, 75000)
    assert out == {"ratio": Decimal("0.7692"), "payable": Decimal("57692.31"), "deduction": Decimal("17307.69")}
    assert out["payable"] + out["deduction"] == Decimal("75000.00")


def test_no_deduction_when_within_limit():
    assert rr(8000, 6500, 1000)["deduction"] == Decimal("0.00")


@pytest.mark.parametrize("args", [(0, 6500, 100), (5000, 0, 100), (5000, 6500, -1)])
def test_rejects_invalid_inputs(args):
    with pytest.raises(ValueError):
        rr(*args)
