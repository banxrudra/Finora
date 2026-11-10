from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from ..models import Category, Transaction
from ..services import analytics as an
from ..services.seed import create_default_categories, generate_demo_data
from ..utils import RANGE_OPTIONS, resolve_range
from ._helpers import back

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    uid, cur = current_user.id, current_user.currency
    rng = resolve_range(session.get("range"))
    summary = an.summary_with_deltas(uid, rng)
    months = 12 if rng.key in ("this_year", "last_12_months") else 6
    monthly = an.monthly_series(uid, months, rng.end)
    cats = an.category_breakdown(uid, rng.start, rng.end)
    trend = an.spending_trend(uid, rng)
    budgets = an.budget_status(uid)
    recent = (Transaction.query.filter_by(user_id=uid)
              .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(6).all())
    inc_spark = an.sparkline(uid, rng, "income")
    exp_spark = an.sparkline(uid, rng, "expense")
    sparks = {
        "balance": an.balance_sparkline(uid, rng),
        "income": inc_spark,
        "expense": exp_spark,
        "savings": [i - e for i, e in zip(inc_spark, exp_spark)],
    }
    # Cumulative savings is a more readable sparkline than daily net.
    run, cum = 0, []
    for v in sparks["savings"]:
        run += v
        cum.append(run)
    sparks["savings"] = cum
    has_data = Transaction.query.filter_by(user_id=uid).first() is not None
    return render_template(
        "pages/dashboard.html",
        rng=rng, summary=summary, monthly=monthly, cats=cats, trend=trend, budgets=budgets,
        recent=recent, sparks=sparks, insights=an.insights(uid, rng, cur), has_data=has_data,
    )


@bp.route("/range", methods=["POST"])
@login_required
def set_range():
    key = request.form.get("range")
    if key in dict(RANGE_OPTIONS):
        session["range"] = key
    return redirect(back("main.dashboard"))


@bp.route("/demo-data", methods=["POST"])
@login_required
def load_demo():
    if Transaction.query.filter_by(user_id=current_user.id).first():
        flash("Sample data can only be loaded into an empty account.", "error")
        return redirect(url_for("main.dashboard"))
    if not Category.query.filter_by(user_id=current_user.id).first():
        create_default_categories(current_user)
    generate_demo_data(current_user)
    flash("Sample data loaded – 12 months of transactions and budgets.", "success")
    return redirect(url_for("main.dashboard"))


@bp.app_template_global()
def today_iso():
    return date.today().isoformat()
