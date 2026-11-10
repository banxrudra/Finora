import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from ..extensions import db
from ..models import Category, Transaction
from ..utils import PAYMENT_METHODS, clean_text, from_minor, parse_amount, parse_date
from ._helpers import back, owned

bp = Blueprint("transactions", __name__, url_prefix="/transactions")

SORTS = {
    "date_desc": (Transaction.date.desc(), Transaction.id.desc()),
    "date_asc": (Transaction.date.asc(), Transaction.id.asc()),
    "amount_desc": (Transaction.amount_minor.desc(),),
    "amount_asc": (Transaction.amount_minor.asc(),),
}


def read_filters(args) -> dict:
    cat = args.get("category", type=int)
    return {
        "q": clean_text(args.get("q"), 80),
        "kind": args.get("kind") if args.get("kind") in ("income", "expense") else "",
        "category": cat,
        "method": args.get("method") if args.get("method") in PAYMENT_METHODS else "",
        "start": parse_date(args.get("start")),
        "end": parse_date(args.get("end")),
        "sort": args.get("sort") if args.get("sort") in SORTS else "date_desc",
    }


def filtered_query(user_id: int, f: dict):
    q = Transaction.query.filter(Transaction.user_id == user_id)
    if f["q"]:
        like = f"%{f['q']}%"
        q = q.filter(or_(Transaction.title.ilike(like), Transaction.notes.ilike(like)))
    if f["kind"]:
        q = q.filter(Transaction.kind == f["kind"])
    if f["category"]:
        q = q.filter(Transaction.category_id == f["category"])
    if f["method"]:
        q = q.filter(Transaction.method == f["method"])
    if f["start"]:
        q = q.filter(Transaction.date >= f["start"])
    if f["end"]:
        q = q.filter(Transaction.date <= f["end"])
    return q.order_by(*SORTS[f["sort"]])


def validate(form) -> tuple[dict, list[str]]:
    errors = []
    title = clean_text(form.get("title"), 80)
    kind = form.get("kind")
    amount = parse_amount(form.get("amount"))
    d = parse_date(form.get("date"))
    method = form.get("method")
    notes = clean_text(form.get("notes"), 255) or None
    category_id = form.get("category_id", type=int)

    if len(title) < 2:
        errors.append("Title must be at least 2 characters.")
    if kind not in ("income", "expense"):
        errors.append("Choose income or expense.")
    if amount is None:
        errors.append("Enter a positive amount with at most two decimals.")
    if d is None:
        errors.append("Enter a valid date.")
    elif d > date.today() + timedelta(days=365) or d.year < 2000:
        errors.append("Date is out of the supported range.")
    if method not in PAYMENT_METHODS:
        errors.append("Choose a payment method.")
    category = None
    if category_id:
        category = db.session.get(Category, category_id)
        if category is None or category.user_id != current_user.id:
            errors.append("Choose a valid category.")
        elif kind in ("income", "expense") and category.kind != kind:
            errors.append(f"“{category.name}” is an {category.kind} category.")
    return {"title": title, "kind": kind, "amount": amount, "date": d, "method": method,
            "notes": notes, "category_id": category.id if category else None}, errors


@bp.route("/")
@login_required
def index():
    f = read_filters(request.args)
    page = max(1, request.args.get("page", 1, type=int))
    pagination = filtered_query(current_user.id, f).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    categories = (Category.query.filter_by(user_id=current_user.id)
                  .order_by(Category.kind.desc(), Category.name).all())
    args = {k: v for k, v in request.args.items() if k != "page" and v}
    active_filters = sum(1 for k in ("category", "method", "start", "end") if f[k])
    sums = dict(filtered_query(current_user.id, f).order_by(None)
                .with_entities(Transaction.kind, func.sum(Transaction.amount_minor))
                .group_by(Transaction.kind).all())
    totals = {"income": from_minor(sums.get("income", 0)), "expense": from_minor(sums.get("expense", 0))}
    totals["net"] = totals["income"] - totals["expense"]
    cat_lookup = {c.id: c for c in categories}
    return render_template("pages/transactions.html", pagination=pagination, f=f, categories=categories,
                           methods=PAYMENT_METHODS, args=args, active_filters=active_filters,
                           totals=totals, cat_lookup=cat_lookup)


@bp.route("/new", methods=["POST"])
@login_required
def create():
    data, errors = validate(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("transactions.index"))
    t = Transaction(user_id=current_user.id, **{k: v for k, v in data.items() if k != "amount"})
    t.amount = data["amount"]
    db.session.add(t)
    db.session.commit()
    flash(f"{'Income' if t.kind == 'income' else 'Expense'} “{t.title}” added.", "success")
    return redirect(back("transactions.index"))


@bp.route("/<int:tid>/edit", methods=["POST"])
@login_required
def update(tid):
    t = owned(Transaction, tid)
    data, errors = validate(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(back("transactions.index"))
    for k, v in data.items():
        setattr(t, k, v)
    db.session.commit()
    flash(f"“{t.title}” updated.", "success")
    return redirect(back("transactions.index"))


@bp.route("/<int:tid>/delete", methods=["POST"])
@login_required
def delete(tid):
    t = owned(Transaction, tid)
    db.session.delete(t)
    db.session.commit()
    flash(f"“{t.title}” deleted.", "success")
    return redirect(back("transactions.index"))


def csv_response(rows, filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Title", "Type", "Category", "Payment method", "Amount", "Currency", "Notes"])
    for t in rows:
        title = t.title
        if title[:1] in ("=", "+", "-", "@"):  # neutralise spreadsheet formula injection
            title = "'" + title
        notes = t.notes or ""
        if notes[:1] in ("=", "+", "-", "@"):
            notes = "'" + notes
        w.writerow([t.date.isoformat(), title, t.kind.title(), t.category.name if t.category else "Uncategorised",
                    t.method, str(t.signed_amount), current_user.currency, notes])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.route("/export.csv")
@login_required
def export():
    f = read_filters(request.args)
    rows = filtered_query(current_user.id, f).all()
    return csv_response(rows, f"finora-transactions-{date.today().isoformat()}.csv")
