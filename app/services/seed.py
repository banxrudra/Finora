"""Default categories and realistic demo data."""
import random
from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Budget, Category, Transaction
from ..utils import DEFAULT_CATEGORIES, add_months, month_end, month_start


def create_default_categories(user) -> None:
    for name, kind, icon, color in DEFAULT_CATEGORIES:
        db.session.add(Category(user_id=user.id, name=name, kind=kind, icon=icon, color=color))
    db.session.commit()


# (title, category, method, low, high, times per month)
_EXPENSES = [
    ("Swiggy order", "Food & Dining", "UPI", 250, 900, 6),
    ("Zomato order", "Food & Dining", "UPI", 300, 1100, 4),
    ("Café Coffee Day", "Food & Dining", "Debit Card", 180, 450, 3),
    ("BigBasket", "Groceries", "UPI", 900, 3200, 3),
    ("Blinkit", "Groceries", "UPI", 250, 1200, 4),
    ("Uber ride", "Transport", "UPI", 150, 650, 5),
    ("Petrol – HP", "Transport", "Credit Card", 1500, 3200, 2),
    ("Amazon", "Shopping", "Credit Card", 600, 5200, 2),
    ("Myntra", "Shopping", "Credit Card", 900, 3800, 1),
    ("PVR Cinemas", "Entertainment", "Credit Card", 500, 1400, 1),
    ("Apollo Pharmacy", "Healthcare", "UPI", 200, 1600, 1),
]
_FIXED = [
    ("House rent", "Housing", "Bank Transfer", 22000, 1),
    ("Electricity – BESCOM", "Utilities", "Net Banking", 1400, 5),
    ("Airtel Fiber", "Utilities", "Credit Card", 999, 7),
    ("Jio Postpaid", "Utilities", "UPI", 599, 9),
    ("Netflix", "Subscriptions", "Credit Card", 649, 12),
    ("Spotify", "Subscriptions", "Credit Card", 119, 14),
    ("Cult.fit membership", "Healthcare", "Credit Card", 1499, 3),
]


def generate_demo_data(user, months: int = 12, seed: int = 42) -> None:
    rng = random.Random(seed + user.id)
    cats = {c.name: c for c in Category.query.filter_by(user_id=user.id).all()}
    today = date.today()
    first = add_months(month_start(today), -(months - 1))
    rows = []

    def add(title, cat, kind, amount, d, method):
        if d > today:
            return
        t = Transaction(user_id=user.id, title=title, kind=kind, date=d, method=method,
                        category_id=cats[cat].id if cat in cats else None)
        t.amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        rows.append(t)

    cur = first
    for m in range(months):
        last = month_end(cur)
        growth = 1 + m * 0.012
        add("Salary – Northwind Labs", "Salary", "income", round(85000 * growth, -2), cur.replace(day=1), "Bank Transfer")
        if rng.random() < 0.75:
            add(rng.choice(["Freelance – UI audit", "Freelance – landing page", "Freelance – dashboard build"]),
                "Freelance", "income", rng.randrange(8000, 26000, 500), cur.replace(day=rng.randint(8, 24)), "Bank Transfer")
        if m % 3 == 2:
            add("Mutual fund dividend", "Investments", "income", rng.randrange(2500, 6500, 50), cur.replace(day=rng.randint(10, 20)), "Bank Transfer")
        for title, cat, method, amount, day in _FIXED:
            add(title, cat, "expense", amount if "Electricity" not in title else rng.randint(1100, 2400), cur.replace(day=min(day, last.day)), method)
        for title, cat, method, lo, hi, per in _EXPENSES:
            n = max(0, per + rng.choice([-1, 0, 0, 1]))
            for _ in range(n):
                add(title, cat, "expense", round(rng.uniform(lo, hi), 2), cur + timedelta(days=rng.randint(0, last.day - 1)), method)
        if m in (4, 10):
            add("Weekend trip – Goa", "Entertainment", "expense", rng.randint(9000, 16000), cur.replace(day=rng.randint(12, 20)), "Credit Card")
        cur = add_months(cur, 1)

    db.session.add_all(rows)
    budgets = {
        None: 60000, "Food & Dining": 7000, "Groceries": 7500, "Transport": 6000, "Shopping": 5000,
        "Entertainment": 2500, "Utilities": 4000, "Subscriptions": 900, "Healthcare": 3000,
    }
    for cat, amount in budgets.items():
        b = Budget(user_id=user.id, category_id=cats[cat].id if cat else None, alert_threshold=80)
        b.amount = Decimal(amount)
        db.session.add(b)
    db.session.commit()
