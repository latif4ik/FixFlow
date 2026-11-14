"""Money helpers (DATA-04): integer minor units (KGS tyiyn, 1 KGS = 100 tyiyn), Decimal only.

Binary floats never touch money. Rounding is deterministic: round half up to an integer
tyiyn (0.5 -> 1, 1.5 -> 2, 2.5 -> 3). Inputs are always nonnegative here.
"""

from decimal import ROUND_HALF_UP, Decimal

CURRENCY = "KGS"
MINOR_PER_MAJOR = 100
QTY_PLACES = Decimal("0.001")


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def labor_cost_minor(labor_minutes: int, labor_rate_minor_per_hour: int) -> int:
    """labor_minutes * rate_per_hour / 60, rounded half up to whole tyiyn."""
    return round_half_up(Decimal(labor_minutes) * Decimal(labor_rate_minor_per_hour) / Decimal(60))


def line_total_minor(quantity: Decimal, unit_price_minor: int) -> int:
    """quantity (<= 3 decimals) * unit price (tyiyn), rounded half up to whole tyiyn."""
    return round_half_up(Decimal(quantity) * Decimal(unit_price_minor))
