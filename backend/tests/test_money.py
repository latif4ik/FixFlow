"""DATA-04: integer minor units, deterministic half-up rounding, no floats."""

from decimal import Decimal

import pytest

from app.core import money


@pytest.mark.parametrize(
    ("minutes", "rate", "expected"),
    [
        (0, 50000, 0),
        (60, 50000, 50000),
        (90, 50000, 75000),
        (1, 50, 1),  # 50/60 = 0.833 -> 1
        (1, 30, 1),  # exactly 0.5 -> rounds UP
        (3, 10, 1),  # exactly 0.5 -> 1
        (1, 29, 0),  # 0.483 -> 0
        (1, 90, 2),  # exactly 1.5 -> 2
        (5, 30, 3),  # exactly 2.5 -> 3 (banker's rounding would give 2)
        (7, 1000, 117),  # 116.67 -> 117
        (1_000_000, 10**9, 16_666_666_666_667),  # large values stay exact
    ],
)
def test_labor_cost_half_up(minutes, rate, expected):
    assert money.labor_cost_minor(minutes, rate) == expected


@pytest.mark.parametrize(
    ("qty", "price", "expected"),
    [
        ("1", 100, 100),
        ("2", 12050, 24100),
        ("1.5", 333, 500),  # 499.5 -> 500
        ("0.5", 1, 1),  # 0.5 -> 1
        ("0.001", 499, 0),  # 0.499 -> 0
        ("0.001", 500, 1),  # 0.5 -> 1
        ("2.5", 1, 3),  # 2.5 -> 3
        ("3.333", 3, 10),  # 9.999 -> 10
        ("0.333", 100, 33),  # 33.3 -> 33
    ],
)
def test_line_total_half_up(qty, price, expected):
    assert money.line_total_minor(Decimal(qty), price) == expected


def test_results_are_ints_never_floats():
    assert type(money.labor_cost_minor(7, 1000)) is int
    assert type(money.line_total_minor(Decimal("1.5"), 333)) is int
    assert money.CURRENCY == "KGS"
