from datetime import date
from decimal import Decimal

from app.utils import format_compact, format_money, from_minor, parse_amount, resolve_range, to_minor


def test_indian_grouping():
    assert format_money(Decimal("12345678.9")) == "₹1,23,45,678.90"
    assert format_money(Decimal("999")) == "₹999.00"
    assert format_money(Decimal("100000")) == "₹1,00,000.00"
    assert format_money(Decimal("-1500.5")) == "−₹1,500.50"
    assert format_money(Decimal("50"), sign=True) == "+₹50.00"


def test_other_currency_grouping():
    assert format_money(Decimal("1234567.5"), "USD") == "$1,234,567.50"


def test_compact():
    assert format_compact(150000) == "₹1.5L"
    assert format_compact(25000000) == "₹2.5Cr"
    assert format_compact(2500, "USD") == "$2.5K"


def test_minor_units_roundtrip_is_exact():
    assert to_minor(Decimal("0.1")) + to_minor(Decimal("0.2")) == to_minor(Decimal("0.3"))
    assert from_minor(to_minor("1999.99")) == Decimal("1999.99")


def test_parse_amount_validation():
    assert parse_amount("1,250.50") == Decimal("1250.50")
    for bad in ("", "abc", "-5", "0", "1.234", "NaN", "Infinity", "1e12"):
        assert parse_amount(bad) is None, bad


def test_previous_period_for_month():
    rng = resolve_range("this_month", date(2026, 3, 15))
    assert (rng.start, rng.end) == (date(2026, 3, 1), date(2026, 3, 31))
    prev = rng.previous()
    assert (prev.start, prev.end) == (date(2026, 2, 1), date(2026, 2, 28))
    q = resolve_range("last_3_months", date(2026, 3, 15)).previous()
    assert (q.start, q.end) == (date(2025, 10, 1), date(2025, 12, 31))
