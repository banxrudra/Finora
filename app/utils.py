"""Money, date and validation helpers shared across the app."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("100000000")  # 10 crore per entry is plenty

CURRENCIES = {
    "INR": {"symbol": "₹", "name": "Indian Rupee", "indian_grouping": True},
    "USD": {"symbol": "$", "name": "US Dollar", "indian_grouping": False},
    "EUR": {"symbol": "€", "name": "Euro", "indian_grouping": False},
    "GBP": {"symbol": "£", "name": "British Pound", "indian_grouping": False},
}

PAYMENT_METHODS = ["UPI", "Debit Card", "Credit Card", "Net Banking", "Cash", "Wallet", "Bank Transfer"]

# Validated categorical palette (fixed order) + neutral slate.
CATEGORY_COLORS = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#6250d6", "#e34948", "#64748b",
]

CATEGORY_ICONS = [
    "home", "utensils", "shopping-cart", "shopping-bag", "car", "fuel", "plane", "bus",
    "zap", "wifi", "smartphone", "tv", "film", "music", "gamepad-2", "heart-pulse",
    "pill", "graduation-cap", "book-open", "shirt", "gift", "coffee", "dumbbell", "baby",
    "paw-print", "shield", "receipt", "landmark", "briefcase", "laptop", "trending-up",
    "piggy-bank", "wallet", "banknote", "building-2", "sparkles", "tag", "wrench",
]

DEFAULT_CATEGORIES = [
    # name, kind, icon, color
    ("Salary", "income", "briefcase", "#1baf7a"),
    ("Freelance", "income", "laptop", "#2a78d6"),
    ("Investments", "income", "trending-up", "#6250d6"),
    ("Other Income", "income", "banknote", "#64748b"),
    ("Housing", "expense", "home", "#2a78d6"),
    ("Food & Dining", "expense", "utensils", "#eb6834"),
    ("Groceries", "expense", "shopping-cart", "#1baf7a"),
    ("Transport", "expense", "car", "#eda100"),
    ("Shopping", "expense", "shopping-bag", "#e87ba4"),
    ("Utilities", "expense", "zap", "#008300"),
    ("Entertainment", "expense", "film", "#6250d6"),
    ("Healthcare", "expense", "heart-pulse", "#e34948"),
    ("Subscriptions", "expense", "receipt", "#64748b"),
]

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


# --------------------------------------------------------------------------- money
def to_minor(value) -> int:
    """Convert a Decimal/str amount to integer minor units (paise)."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    return int((dec.quantize(CENT, rounding=ROUND_HALF_UP) * 100).to_integral_value())


def from_minor(value) -> Decimal:
    return (Decimal(int(value or 0)) / 100).quantize(CENT)


def parse_amount(raw) -> Decimal | None:
    """Parse user input into a positive Decimal, or None when invalid."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("₹", "").replace("$", "")
    if not text:
        return None
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return None
    if not dec.is_finite() or dec <= 0 or dec > MAX_AMOUNT:
        return None
    if dec != dec.quantize(CENT):  # more than two decimal places
        return None
    return dec.quantize(CENT)


def _group_indian(int_part: str) -> str:
    if len(int_part) <= 3:
        return int_part
    last3, rest = int_part[-3:], int_part[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups) + "," + last3


def format_money(value, currency: str = "INR", decimals: bool = True, sign: bool = False) -> str:
    dec = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    info = CURRENCIES.get(currency, CURRENCIES["INR"])
    negative = dec < 0
    dec = abs(dec).quantize(CENT if decimals else Decimal("1"), rounding=ROUND_HALF_UP)
    text = f"{dec:.2f}" if decimals else f"{dec:.0f}"
    int_part, _, frac = text.partition(".")
    int_part = _group_indian(int_part) if info["indian_grouping"] else f"{int(int_part):,}"
    body = info["symbol"] + int_part + (f".{frac}" if frac else "")
    if negative:
        return "−" + body
    if sign and dec > 0:
        return "+" + body
    return body


def format_compact(value, currency: str = "INR") -> str:
    """Short axis-friendly label: ₹1.2L, ₹3.4Cr for INR; $1.2K / $3.4M otherwise."""
    dec = Decimal(str(value or 0))
    info = CURRENCIES.get(currency, CURRENCIES["INR"])
    sym, a = info["symbol"], abs(dec)
    if info["indian_grouping"]:
        steps = [(Decimal("10000000"), "Cr"), (Decimal("100000"), "L"), (Decimal("1000"), "K")]
    else:
        steps = [(Decimal("1000000000"), "B"), (Decimal("1000000"), "M"), (Decimal("1000"), "K")]
    for size, suffix in steps:
        if a >= size:
            num = (a / size).quantize(Decimal("0.1"))
            num_s = f"{num:.1f}".rstrip("0").rstrip(".")
            return ("−" if dec < 0 else "") + f"{sym}{num_s}{suffix}"
    return ("−" if dec < 0 else "") + f"{sym}{a:.0f}"


def pct_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if not previous:
        return None
    return ((current - previous) / abs(previous) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- dates
def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def parse_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        return None


def parse_month(raw) -> date | None:
    """Parse 'YYYY-MM' into the first day of that month."""
    if not raw:
        return None
    try:
        y, m = str(raw).split("-")
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class DateRange:
    key: str
    label: str
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> "DateRange":
        """The equally long period immediately preceding this one."""
        if self.start == month_start(self.start) and self.end == month_end(self.end):
            months = (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1
            start = add_months(self.start, -months)
            return DateRange("prev", "Previous period", start, month_end(add_months(start, months - 1)))
        end = self.start - timedelta(days=1)
        return DateRange("prev", "Previous period", end - timedelta(days=self.days - 1), end)


RANGE_OPTIONS = [
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("last_3_months", "Last 3 months"),
    ("last_6_months", "Last 6 months"),
    ("this_year", "This year"),
    ("last_12_months", "Last 12 months"),
]


def resolve_range(key: str | None, today: date | None = None) -> DateRange:
    today = today or date.today()
    ms = month_start(today)
    labels = dict(RANGE_OPTIONS)
    key = key if key in labels else "this_month"
    if key == "last_month":
        s = add_months(ms, -1)
        return DateRange(key, labels[key], s, month_end(s))
    if key == "last_3_months":
        return DateRange(key, labels[key], add_months(ms, -2), month_end(today))
    if key == "last_6_months":
        return DateRange(key, labels[key], add_months(ms, -5), month_end(today))
    if key == "this_year":
        return DateRange(key, labels[key], date(today.year, 1, 1), month_end(today))
    if key == "last_12_months":
        return DateRange(key, labels[key], add_months(ms, -11), month_end(today))
    return DateRange("this_month", labels["this_month"], ms, month_end(today))


def clean_text(raw, max_len: int) -> str:
    return re.sub(r"\s+", " ", str(raw or "")).strip()[:max_len]
