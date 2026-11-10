from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from ..services.seed import create_default_categories
from ..utils import EMAIL_RE, clean_text

bp = Blueprint("auth", __name__)


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    errors, form = {}, {}
    if request.method == "POST":
        form = {"email": clean_text(request.form.get("email"), 120).lower()}
        password = request.form.get("password", "")
        user = User.query.filter_by(email=form["email"]).first()
        if not user or not user.check_password(password):
            errors["form"] = "Incorrect email or password."
        else:
            session.clear()
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
    return render_template("auth/login.html", errors=errors, form=form), (400 if errors else 200)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    errors, form = {}, {}
    if request.method == "POST":
        form = {
            "name": clean_text(request.form.get("name"), 80),
            "email": clean_text(request.form.get("email"), 120).lower(),
        }
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(form["name"]) < 2:
            errors["name"] = "Enter your full name."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Enter a valid email address."
        elif User.query.filter_by(email=form["email"]).first():
            errors["email"] = "An account with this email already exists."
        if len(password) < 8:
            errors["password"] = "Use at least 8 characters."
        elif password != confirm:
            errors["confirm"] = "Passwords do not match."
        if not errors:
            user = User(name=form["name"], email=form["email"])
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            create_default_categories(user)
            login_user(user)
            flash(f"Welcome to Finora, {user.first_name}! Your account is ready.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html", errors=errors, form=form), (400 if errors else 200)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()  # drop pending flashes, range preference etc. from the previous user
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
