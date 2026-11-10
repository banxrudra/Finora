from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from ..extensions import db
from ..models import Budget, Category, Transaction, User
from ..utils import CURRENCIES, EMAIL_RE, clean_text

bp = Blueprint("settings", __name__, url_prefix="/settings")

THEMES = ("light", "dark", "system")


@bp.route("/")
@login_required
def index():
    tab = request.args.get("tab", "profile")
    if tab not in ("profile", "preferences", "security", "data"):
        tab = "profile"
    stats = {
        "transactions": Transaction.query.filter_by(user_id=current_user.id).count(),
        "categories": Category.query.filter_by(user_id=current_user.id).count(),
        "budgets": Budget.query.filter_by(user_id=current_user.id).count(),
    }
    return render_template("pages/settings.html", tab=tab, stats=stats)


@bp.route("/profile", methods=["POST"])
@login_required
def profile():
    name = clean_text(request.form.get("name"), 80)
    email = clean_text(request.form.get("email"), 120).lower()
    errors = []
    if len(name) < 2:
        errors.append("Enter your full name.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    elif email != current_user.email and User.query.filter_by(email=email).first():
        errors.append("That email is already in use.")
    if errors:
        for e in errors:
            flash(e, "error")
    else:
        current_user.name, current_user.email = name, email
        db.session.commit()
        flash("Profile updated.", "success")
    return redirect(url_for("settings.index", tab="profile"))


@bp.route("/preferences", methods=["POST"])
@login_required
def preferences():
    currency = request.form.get("currency")
    theme = request.form.get("theme")
    if currency not in CURRENCIES or theme not in THEMES:
        flash("Choose a valid currency and theme.", "error")
    else:
        current_user.currency, current_user.theme = currency, theme
        db.session.commit()
        flash("Preferences saved.", "success")
    return redirect(url_for("settings.index", tab="preferences"))


@bp.route("/theme", methods=["POST"])
@login_required
def theme():
    """Persist the topbar theme toggle (called via fetch with the CSRF header)."""
    value = (request.get_json(silent=True) or {}).get("theme") or request.form.get("theme")
    if value not in THEMES:
        return jsonify({"ok": False}), 400
    current_user.theme = value
    db.session.commit()
    return jsonify({"ok": True, "theme": value})


@bp.route("/password", methods=["POST"])
@login_required
def password():
    current = request.form.get("current", "")
    new = request.form.get("new", "")
    confirm = request.form.get("confirm", "")
    if not current_user.check_password(current):
        flash("Your current password is incorrect.", "error")
    elif len(new) < 8:
        flash("New password must be at least 8 characters.", "error")
    elif new != confirm:
        flash("New passwords do not match.", "error")
    elif new == current:
        flash("New password must be different from the current one.", "error")
    else:
        current_user.set_password(new)
        db.session.commit()
        flash("Password changed.", "success")
    return redirect(url_for("settings.index", tab="security"))


@bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    if not current_user.check_password(request.form.get("password", "")):
        flash("Password is incorrect – account not deleted.", "error")
        return redirect(url_for("settings.index", tab="data"))
    user = db.session.get(User, current_user.id)
    logout_user()
    Transaction.query.filter_by(user_id=user.id).delete()
    Budget.query.filter_by(user_id=user.id).delete()
    Category.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash("Your account and all data were permanently deleted.", "info")
    return redirect(url_for("auth.login"))
