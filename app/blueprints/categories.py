from datetime import date

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import Budget, Category, Transaction
from ..utils import CATEGORY_COLORS, CATEGORY_ICONS, HEX_RE, clean_text, from_minor, month_end, month_start
from ._helpers import back, owned

bp = Blueprint("categories", __name__, url_prefix="/categories")


def _validate(form, category=None):
    errors = []
    name = clean_text(form.get("name"), 40)
    kind = form.get("kind")
    icon = form.get("icon")
    color = form.get("color", "")
    if len(name) < 2:
        errors.append("Name must be at least 2 characters.")
    if kind not in ("income", "expense"):
        errors.append("Choose income or expense.")
    if icon not in CATEGORY_ICONS:
        errors.append("Choose an icon.")
    if not HEX_RE.match(color):
        errors.append("Choose a colour.")
    if not errors:
        dup = (Category.query.filter(Category.user_id == current_user.id, Category.kind == kind,
                                     func.lower(Category.name) == name.lower()).first())
        if dup and (category is None or dup.id != category.id):
            errors.append(f"You already have an {kind} category called “{name}”.")
        if category and kind != category.kind and category.transactions.first():
            errors.append("Type can't change once a category has transactions.")
    return {"name": name, "kind": kind, "icon": icon, "color": color.lower()}, errors


@bp.route("/")
@login_required
def index():
    uid = current_user.id
    ms, me = month_start(date.today()), month_end(date.today())
    stats = dict(
        (cid, (cnt, s)) for cid, cnt, s in db.session.query(
            Transaction.category_id, func.count(Transaction.id), func.sum(Transaction.amount_minor))
        .filter(Transaction.user_id == uid).group_by(Transaction.category_id).all()
    )
    month = dict(
        db.session.query(Transaction.category_id, func.sum(Transaction.amount_minor))
        .filter(Transaction.user_id == uid, Transaction.date >= ms, Transaction.date <= me)
        .group_by(Transaction.category_id).all()
    )
    cats = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    rows = {"expense": [], "income": []}
    for c in cats:
        cnt, total = stats.get(c.id, (0, 0))
        rows[c.kind].append({"c": c, "count": cnt, "total": from_minor(total), "month": from_minor(month.get(c.id, 0))})
    tab = request.args.get("tab", "expense")
    if tab not in rows:
        tab = "expense"
    return render_template("pages/categories.html", rows=rows, tab=tab,
                           icons=CATEGORY_ICONS, colors=CATEGORY_COLORS)


@bp.route("/new", methods=["POST"])
@login_required
def create():
    data, errors = _validate(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("categories.index"))
    c = Category(user_id=current_user.id, **data)
    db.session.add(c)
    db.session.commit()
    flash(f"Category “{c.name}” created.", "success")
    return redirect(back("categories.index"))


@bp.route("/<int:cid>/edit", methods=["POST"])
@login_required
def update(cid):
    c = owned(Category, cid)
    data, errors = _validate(request.form, c)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("categories.index"))
    for k, v in data.items():
        setattr(c, k, v)
    db.session.commit()
    flash(f"Category “{c.name}” updated.", "success")
    return redirect(back("categories.index"))


@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = owned(Category, cid)
    # Keep the money history: transactions become uncategorised.
    Transaction.query.filter_by(user_id=current_user.id, category_id=c.id).update({"category_id": None})
    Budget.query.filter_by(user_id=current_user.id, category_id=c.id).delete()
    db.session.delete(c)
    db.session.commit()
    flash(f"Category “{c.name}” deleted. Its transactions are now uncategorised.", "success")
    return redirect(back("categories.index"))
