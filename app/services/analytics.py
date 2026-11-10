"""Aggregations for dashboard, analytics, reports and notifications.

Every query here is scoped by ``user_id`` – callers never pass raw queries in.
Sums are computed on integer minor units and converted to ``Decimal`` at the end.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import Budget, Category, Transaction
from ..utils import (
    DateRange,
    add_months,
    format_money,
    from_minor,
    month_end,
    month_start,
    pct_change,
)

ZERO = Decimal("0.00")


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    if not whole:
        return Decimal("0.0")
    return (part / whole * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _base(user_id: int, start: date | None = None, end: date | None = None):
    q = db.session.query(Transaction).filter(Transaction.user_id == user_id)
    if start:
        q = q.filter(Transaction.date >= start)
    if end:
        q = q.filter(Transaction.date <= end)
    return q


def totals(user_id: int, start: date | None, end: date | None) -> dict:
    rows = (
        _base(user_id, start, end)
        .with_entities(Transaction.kind, func.coalesce(func.sum(Transaction.amount_minor), 0), func.count())
        .group_by(Transaction.kind)
        .all()
    )
    data = {k: (from_minor(s), c) for k, s, c in rows}
    income, n_in = data.get("income", (ZERO, 0))
    expense, n_ex = data.get("expense", (ZERO, 0))
    net = income - expense
    return {
        "income": income,
        "expense": expense,
        "net": net,
        "savings_rate": _pct(net, income) if income else Decimal("0.0"),
        "count": n_in + n_ex,
        "income_count": n_in,
        "expense_count": n_ex,
    }


def balance(user_id: int, as_of: date | None = None) -> Decimal:
    t = totals(user_id, None, as_of or date.today())
    return t["net"]


def category_breakdown(user_id: int, start: date | None, end: date | None, kind: str = "expense") -> list[dict]:
    rows = (
        _base(user_id, start, end)
        .filter(Transaction.kind == kind)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .with_entities(
            Category.id, Category.name, Category.color, Category.icon,
            func.sum(Transaction.amount_minor), func.count(Transaction.id),
        )
        .group_by(Category.id)
        .order_by(func.sum(Transaction.amount_minor).desc())
        .all()
    )
    total = sum((from_minor(r[4]) for r in rows), ZERO)
    out = []
    for cid, name, color, icon, s, c in rows:
        amt = from_minor(s)
        out.append({
            "id": cid,
            "name": name or "Uncategorised",
            "color": color or "#94a3b8",
            "icon": icon or "tag",
            "amount": amt,
            "count": c,
            "pct": _pct(amt, total),
        })
    return out


def monthly_series(user_id: int, months: int = 6, end: date | None = None) -> dict:
    """Income, expense and savings per calendar month for the last ``months`` months."""
    end = month_end(end or date.today())
    start = add_months(month_start(end), -(months - 1))
    rows = (
        _base(user_id, start, end)
        .with_entities(Transaction.date, Transaction.kind, Transaction.amount_minor)
        .all()
    )
    buckets = defaultdict(lambda: {"income": 0, "expense": 0})
    for d, kind, amt in rows:
        buckets[(d.year, d.month)][kind] += amt
    labels, keys, income, expense, savings = [], [], [], [], []
    cur = start
    for _ in range(months):
        b = buckets[(cur.year, cur.month)]
        labels.append(cur.strftime("%b %Y") if months > 12 else cur.strftime("%b"))
        keys.append(cur.strftime("%Y-%m"))
        i, e = from_minor(b["income"]), from_minor(b["expense"])
        income.append(i)
        expense.append(e)
        savings.append(i - e)
        cur = add_months(cur, 1)
    return {"labels": labels, "keys": keys, "income": income, "expense": expense, "savings": savings}


def daily_series(user_id: int, start: date, end: date, kind: str = "expense") -> dict:
    rows = (
        _base(user_id, start, end)
        .filter(Transaction.kind == kind)
        .with_entities(Transaction.date, func.sum(Transaction.amount_minor))
        .group_by(Transaction.date)
        .all()
    )
    by_day = {d: s for d, s in rows}
    labels, values = [], []
    d = start
    while d <= end:
        labels.append(d.isoformat())
        values.append(from_minor(by_day.get(d, 0)))
        d += timedelta(days=1)
    return {"labels": labels, "values": values}


def spending_trend(user_id: int, rng: DateRange) -> dict:
    """Cumulative spend for this period vs. the previous equally long period."""
    prev = rng.previous()
    cur = daily_series(user_id, rng.start, rng.end)
    old = daily_series(user_id, prev.start, prev.end)
    today = date.today()

    def cumulate(values, labels=None, stop=None):
        out, run = [], ZERO
        for i, v in enumerate(values):
            if stop and labels and date.fromisoformat(labels[i]) > stop:
                out.append(None)
                continue
            run += v
            out.append(run)
        return out

    n = max(len(cur["values"]), len(old["values"]))
    # Bucket into weeks when the range is long so the line stays readable.
    if n > 62:
        def weekly(vals):
            return [sum(vals[i:i + 7], ZERO) for i in range(0, len(vals), 7)]
        cur_vals, old_vals = weekly(cur["values"]), weekly(old["values"])
        labels = [date.fromisoformat(cur["labels"][i]).strftime("%d %b") for i in range(0, len(cur["labels"]), 7)]
        cur_c = cumulate(cur_vals)
        # do not draw future weeks
        cutoff = sum(1 for i in range(0, len(cur["labels"]), 7) if date.fromisoformat(cur["labels"][i]) <= today)
        cur_c = [v if idx < cutoff else None for idx, v in enumerate(cur_c)]
        old_c = cumulate(old_vals)
    else:
        labels = [date.fromisoformat(x).strftime("%d %b") for x in cur["labels"]]
        cur_c = cumulate(cur["values"], cur["labels"], today)
        old_c = cumulate(old["values"])
    old_c = (old_c + [None] * len(labels))[: len(labels)]
    return {"labels": labels, "current": cur_c, "previous": old_c, "granularity": "week" if n > 62 else "day"}


def budget_status(user_id: int, month: date | None = None) -> dict:
    month = month_start(month or date.today())
    end = month_end(month)
    spent_rows = (
        _base(user_id, month, end)
        .filter(Transaction.kind == "expense")
        .with_entities(Transaction.category_id, func.sum(Transaction.amount_minor))
        .group_by(Transaction.category_id)
        .all()
    )
    spent_by_cat = {cid: from_minor(s) for cid, s in spent_rows}
    total_spent = sum(spent_by_cat.values(), ZERO)

    budgets = Budget.query.filter_by(user_id=user_id).all()
    items, overall = [], None
    for b in budgets:
        spent = total_spent if b.category_id is None else spent_by_cat.get(b.category_id, ZERO)
        pct = _pct(spent, b.amount)
        if pct >= 100:
            status = "over"
        elif pct >= b.alert_threshold:
            status = "warning"
        else:
            status = "ok"
        item = {
            "budget": b,
            "id": b.id,
            "category": b.category,
            "name": b.category.name if b.category else "Overall monthly budget",
            "icon": b.category.icon if b.category else "wallet",
            "color": b.category.color if b.category else "#0f766e",
            "amount": b.amount,
            "spent": spent,
            "remaining": b.amount - spent,
            "pct": pct,
            "bar_pct": min(pct, Decimal("100")),
            "status": status,
            "threshold": b.alert_threshold,
        }
        if b.category_id is None:
            overall = item
        else:
            items.append(item)
    items.sort(key=lambda x: x["pct"], reverse=True)
    cat_total = sum((i["amount"] for i in items), ZERO)
    cat_spent = sum((i["spent"] for i in items), ZERO)
    return {
        "month": month,
        "rows": items,
        "overall": overall,
        "total_budget": overall["amount"] if overall else cat_total,
        "total_spent": total_spent if overall else cat_spent,
        "over_count": sum(1 for i in items if i["status"] == "over"),
        "warning_count": sum(1 for i in items if i["status"] == "warning"),
    }


def budget_vs_actual(user_id: int, month: date | None = None) -> dict:
    status = budget_status(user_id, month)
    items = status["rows"]
    return {
        "labels": [i["name"] for i in items],
        "budget": [i["amount"] for i in items],
        "actual": [i["spent"] for i in items],
    }


def insights(user_id: int, rng: DateRange, currency: str) -> list[dict]:
    """Plain-language observations derived from the user's data."""
    out: list[dict] = []
    cur = totals(user_id, rng.start, rng.end)
    prev_rng = rng.previous()
    prev = totals(user_id, prev_rng.start, prev_rng.end)

    if cur["count"] == 0:
        return [{
            "tone": "neutral", "icon": "sparkles", "title": "No activity in this period",
            "text": "Add a few transactions and insights about your spending will appear here.",
        }]

    # Savings rate
    rate = cur["savings_rate"]
    if cur["income"]:
        if rate >= 20:
            out.append({"tone": "good", "icon": "piggy-bank", "title": f"You saved {rate}% of your income",
                        "text": f"{format_money(cur['net'], currency)} kept this period – above the 20% guideline."})
        elif rate >= 0:
            out.append({"tone": "warning", "icon": "piggy-bank", "title": f"Savings rate is {rate}%",
                        "text": "Aim for at least 20%. Trimming your top category is the quickest lever."})
        else:
            out.append({"tone": "critical", "icon": "alert-triangle", "title": "Spending exceeded income",
                        "text": f"You spent {format_money(-cur['net'], currency)} more than you earned this period."})

    # Spending change vs previous period
    change = pct_change(cur["expense"], prev["expense"])
    if change is not None and abs(change) >= 5:
        if change > 0:
            out.append({"tone": "warning", "icon": "trending-up", "title": f"Spending up {change}%",
                        "text": f"Compared with the previous period ({format_money(prev['expense'], currency)})."})
        else:
            out.append({"tone": "good", "icon": "trending-down", "title": f"Spending down {abs(change)}%",
                        "text": f"Compared with the previous period ({format_money(prev['expense'], currency)})."})

    # Largest category and its biggest mover
    cats = category_breakdown(user_id, rng.start, rng.end)
    if cats:
        top = cats[0]
        out.append({"tone": "neutral", "icon": top["icon"], "title": f"{top['name']} is your largest expense",
                    "text": f"{format_money(top['amount'], currency)} – {top['pct']}% of total spending across {top['count']} transaction{'s' if top['count'] != 1 else ''}."})
        prev_cats = {c["id"]: c["amount"] for c in category_breakdown(user_id, prev_rng.start, prev_rng.end)}
        movers = []
        for c in cats:
            p = prev_cats.get(c["id"])
            if p and p >= Decimal("500"):
                ch = pct_change(c["amount"], p)
                if ch is not None and ch >= 25:
                    movers.append((ch, c))
        if movers:
            ch, c = max(movers, key=lambda x: x[0])
            out.append({"tone": "warning", "icon": "flame", "title": f"{c['name']} jumped {ch}%",
                        "text": f"{format_money(c['amount'], currency)} vs {format_money(prev_cats[c['id']], currency)} last period."})

    # Budgets
    bs = budget_status(user_id)
    over = [i for i in bs["rows"] if i["status"] == "over"]
    if over:
        names = ", ".join(i["name"] for i in over[:2])
        out.append({"tone": "critical", "icon": "octagon-alert", "title": f"{len(over)} budget{'s' if len(over) > 1 else ''} exceeded",
                    "text": f"{names}{' and more' if len(over) > 2 else ''} went over the monthly limit."})
    elif bs["rows"]:
        out.append({"tone": "good", "icon": "shield-check", "title": "All budgets on track",
                    "text": "No category has exceeded its monthly limit so far."})

    # Average daily spend
    days_elapsed = max(1, (min(rng.end, date.today()) - rng.start).days + 1)
    avg = (cur["expense"] / days_elapsed).quantize(Decimal("0.01"))
    out.append({"tone": "neutral", "icon": "calendar-days", "title": f"{format_money(avg, currency)} average daily spend",
                "text": f"Across {days_elapsed} day{'s' if days_elapsed != 1 else ''} in {rng.label.lower()}."})
    return out[:5]


def notifications(user_id: int, currency: str) -> list[dict]:
    """Live alerts: budgets crossing their thresholds and unusually large expenses."""
    items = []
    bs = budget_status(user_id)
    for i in bs["rows"] + ([bs["overall"]] if bs["overall"] else []):
        if i["status"] == "over":
            items.append({"tone": "critical", "icon": "octagon-alert", "title": f"{i['name']} budget exceeded",
                          "text": f"{format_money(i['spent'], currency)} of {format_money(i['amount'], currency)} used ({i['pct']}%)",
                          "href": "budgets"})
        elif i["status"] == "warning":
            items.append({"tone": "warning", "icon": "triangle-alert", "title": f"{i['name']} at {i['pct']}%",
                          "text": f"{format_money(i['remaining'], currency)} left this month",
                          "href": "budgets"})
    # Large expenses in the last 7 days (> 3x median expense of the last 90 days)
    recent_start = date.today() - timedelta(days=90)
    amounts = sorted(
        a for (a,) in _base(user_id, recent_start, date.today())
        .filter(Transaction.kind == "expense").with_entities(Transaction.amount_minor).all()
    )
    if len(amounts) >= 8:
        median = amounts[len(amounts) // 2]
        big = (
            _base(user_id, date.today() - timedelta(days=7), date.today())
            .filter(Transaction.kind == "expense", Transaction.amount_minor >= median * 3)
            .order_by(Transaction.amount_minor.desc()).limit(3).all()
        )
        for t in big:
            items.append({"tone": "neutral", "icon": "receipt", "title": f"Large expense: {t.title}",
                          "text": f"{format_money(t.amount, currency)} on {t.date.strftime('%d %b')}",
                          "href": "transactions"})
    return items[:8]


def summary_with_deltas(user_id: int, rng: DateRange) -> dict:
    cur = totals(user_id, rng.start, rng.end)
    prev_rng = rng.previous()
    prev = totals(user_id, prev_rng.start, prev_rng.end)
    bal = balance(user_id)
    bal_prev = balance(user_id, prev_rng.end)
    return {
        "balance": bal,
        "income": cur["income"],
        "expense": cur["expense"],
        "savings": cur["net"],
        "savings_rate": cur["savings_rate"],
        "count": cur["count"],
        "delta": {
            "balance": pct_change(bal, bal_prev),
            "income": pct_change(cur["income"], prev["income"]),
            "expense": pct_change(cur["expense"], prev["expense"]),
            "savings": pct_change(cur["net"], prev["net"]),
        },
        "prev_label": prev_rng,
    }


def balance_sparkline(user_id: int, rng: DateRange) -> list[Decimal]:
    """Running balance at the end of each day in range (sampled to ≤ 30 points)."""
    opening = balance(user_id, rng.start - timedelta(days=1))
    inc = daily_series(user_id, rng.start, rng.end, "income")["values"]
    exp = daily_series(user_id, rng.start, rng.end, "expense")["values"]
    today = date.today()
    out, run = [], opening
    for idx, (i, e) in enumerate(zip(inc, exp)):
        if rng.start + timedelta(days=idx) > today:
            break
        run += i - e
        out.append(run)
    return _sample(out)


def _sample(values: list, n: int = 30) -> list:
    if len(values) <= n:
        return values
    step = len(values) / n
    return [values[int(i * step)] for i in range(n - 1)] + [values[-1]]


def sparkline(user_id: int, rng: DateRange, kind: str) -> list[Decimal]:
    ser = daily_series(user_id, rng.start, min(rng.end, date.today()), kind)["values"]
    if len(ser) > 45:  # weekly buckets for long ranges
        ser = [sum(ser[i:i + 7], ZERO) for i in range(0, len(ser), 7)]
    return _sample(ser)
