from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from ..services import analytics as an
from ..utils import CURRENCIES, add_months, month_end, month_start

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

PERIODS = {"3": 3, "6": 6, "12": 12}


def _num(values):
    return [float(v) if v is not None else None for v in values]


def build_payload(user_id: int, months: int) -> dict:
    end = month_end(date.today())
    start = add_months(month_start(end), -(months - 1))
    monthly = an.monthly_series(user_id, months, end)
    cats = an.category_breakdown(user_id, start, end)
    inc_cats = an.category_breakdown(user_id, start, end, "income")
    # Spending trend: monthly expense with a 3-month moving average.
    exp = monthly["expense"]
    avg = []
    for i in range(len(exp)):
        window = exp[max(0, i - 2): i + 1]
        avg.append(sum(window, Decimal(0)) / len(window))
    bva = an.budget_vs_actual(user_id)
    totals = an.totals(user_id, start, end)
    rates = [
        float((s / i * 100).quantize(Decimal("0.1"))) if i else None
        for s, i in zip(monthly["savings"], monthly["income"])
    ]
    return {
        "currency": current_user.currency,
        "symbol": CURRENCIES[current_user.currency]["symbol"],
        "months": months,
        "labels": monthly["labels"],
        "income": _num(monthly["income"]),
        "expense": _num(exp),
        "savings": _num(monthly["savings"]),
        "savings_rate": rates,
        "expense_avg": _num(avg),
        "categories": [{"name": c["name"], "color": c["color"], "amount": float(c["amount"]), "pct": float(c["pct"]),
                        "count": c["count"]} for c in cats],
        "income_categories": [{"name": c["name"], "color": c["color"], "amount": float(c["amount"]),
                               "pct": float(c["pct"])} for c in inc_cats],
        "budget": {"labels": bva["labels"], "budget": _num(bva["budget"]), "actual": _num(bva["actual"]),
                   "month": date.today().strftime("%B %Y")},
        "totals": {k: float(v) if isinstance(v, Decimal) else v for k, v in totals.items()},
    }


@bp.route("/")
@login_required
def index():
    period = request.args.get("period", "6")
    months = PERIODS.get(period, 6)
    payload = build_payload(current_user.id, months)
    return render_template("pages/analytics.html", payload=payload, period=str(months))


@bp.route("/data")
@login_required
def data():
    months = PERIODS.get(request.args.get("period", "6"), 6)
    return jsonify(build_payload(current_user.id, months))
