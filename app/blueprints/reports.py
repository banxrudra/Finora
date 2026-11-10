from datetime import date
from decimal import Decimal

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from ..models import Transaction
from ..services import analytics as an
from ..utils import add_months, month_end, month_start, parse_date
from .transactions import csv_response

bp = Blueprint("reports", __name__, url_prefix="/reports")

PRESETS = [
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("quarter", "Last 3 months"),
    ("ytd", "Year to date"),
    ("year", "Last 12 months"),
]


def _resolve(args):
    today = date.today()
    preset = args.get("preset")
    start, end = parse_date(args.get("start")), parse_date(args.get("end"))
    if start and end:
        if start > end:
            start, end = end, start
        return start, end, "custom"
    ms = month_start(today)
    if preset == "last_month":
        s = add_months(ms, -1)
        return s, month_end(s), preset
    if preset == "quarter":
        return add_months(ms, -2), month_end(today), preset
    if preset == "ytd":
        return date(today.year, 1, 1), today, preset
    if preset == "year":
        return add_months(ms, -11), month_end(today), preset
    return ms, month_end(today), "this_month"


@bp.route("/")
@login_required
def index():
    uid = current_user.id
    start, end, preset = _resolve(request.args)
    totals = an.totals(uid, start, end)
    exp_cats = an.category_breakdown(uid, start, end, "expense")
    inc_cats = an.category_breakdown(uid, start, end, "income")
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    monthly = an.monthly_series(uid, max(1, min(months, 24)), end) if months > 1 else None
    rows = []
    if monthly:
        for i, label in enumerate(monthly["keys"]):
            m = date.fromisoformat(label + "-01")
            rows.append({"label": m.strftime("%B %Y"), "income": monthly["income"][i],
                         "expense": monthly["expense"][i], "net": monthly["savings"][i]})
    largest = (Transaction.query.filter(Transaction.user_id == uid, Transaction.kind == "expense",
                                        Transaction.date >= start, Transaction.date <= end)
               .order_by(Transaction.amount_minor.desc()).limit(5).all())
    days = max(1, (min(end, date.today()) - start).days + 1)
    return render_template("pages/reports.html", start=start, end=end, preset=preset, presets=PRESETS,
                           totals=totals, exp_cats=exp_cats, inc_cats=inc_cats, monthly_rows=rows,
                           largest=largest, avg_daily=(totals["expense"] / days).quantize(Decimal("0.01")),
                           generated=date.today())


@bp.route("/export.csv")
@login_required
def export():
    start, end, _ = _resolve(request.args)
    rows = (Transaction.query.filter(Transaction.user_id == current_user.id,
                                     Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date.asc(), Transaction.id.asc()).all())
    return csv_response(rows, f"finora-report-{start.isoformat()}-to-{end.isoformat()}.csv")
