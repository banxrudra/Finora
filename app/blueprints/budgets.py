from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Budget, Category
from ..services.analytics import budget_status
from ..utils import add_months, month_start, parse_amount, parse_month
from ._helpers import back, owned

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _validate(form, budget=None):
    errors = []
    amount = parse_amount(form.get("amount"))
    threshold = form.get("alert_threshold", type=int)
    raw_cat = form.get("category_id", "")
    category = None
    if raw_cat in ("", "overall"):
        category = None
    else:
        try:
            category = db.session.get(Category, int(raw_cat))
        except ValueError:
            category = None
        if category is None or category.user_id != current_user.id or category.kind != "expense":
            errors.append("Choose a valid expense category.")
            category = None
    if amount is None:
        errors.append("Enter a positive budget amount.")
    if threshold is None or not 50 <= threshold <= 100:
        errors.append("Alert threshold must be between 50% and 100%.")
    if not errors:
        dup = Budget.query.filter_by(user_id=current_user.id, category_id=category.id if category else None).first()
        if dup and (budget is None or dup.id != budget.id):
            errors.append(f"A budget for {category.name if category else 'overall spending'} already exists – edit it instead.")
    return {"amount": amount, "alert_threshold": threshold, "category_id": category.id if category else None}, errors


@bp.route("/")
@login_required
def index():
    month = parse_month(request.args.get("month")) or month_start(date.today())
    status = budget_status(current_user.id, month)
    budgeted = {i["category"].id for i in status["rows"]}
    expense_cats = (Category.query.filter_by(user_id=current_user.id, kind="expense")
                    .order_by(Category.name).all())
    sort = request.args.get("sort", "usage")
    items = status["rows"]
    if sort == "name":
        items = sorted(items, key=lambda i: i["name"].lower())
    elif sort == "amount":
        items = sorted(items, key=lambda i: i["amount"], reverse=True)
    return render_template(
        "pages/budgets.html", status=status, items=items, sort=sort, month=month,
        prev_month=add_months(month, -1), next_month=add_months(month, 1),
        is_current=month == month_start(date.today()),
        expense_cats=expense_cats, budgeted=budgeted,
    )


@bp.route("/new", methods=["POST"])
@login_required
def create():
    data, errors = _validate(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("budgets.index"))
    b = Budget(user_id=current_user.id, category_id=data["category_id"], alert_threshold=data["alert_threshold"])
    b.amount = data["amount"]
    db.session.add(b)
    db.session.commit()
    flash("Budget created.", "success")
    return redirect(back("budgets.index"))


@bp.route("/<int:bid>/edit", methods=["POST"])
@login_required
def update(bid):
    b = owned(Budget, bid)
    data, errors = _validate(request.form, b)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("budgets.index"))
    b.category_id = data["category_id"]
    b.alert_threshold = data["alert_threshold"]
    b.amount = data["amount"]
    db.session.commit()
    flash("Budget updated.", "success")
    return redirect(back("budgets.index"))


@bp.route("/<int:bid>/delete", methods=["POST"])
@login_required
def delete(bid):
    b = owned(Budget, bid)
    db.session.delete(b)
    db.session.commit()
    flash("Budget removed.", "success")
    return redirect(back("budgets.index"))
