import json
from datetime import date
from decimal import Decimal

import click
from flask import Flask, render_template, request, session
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from markupsafe import Markup

from .config import Config
from .extensions import csrf, db, login_manager
from .utils import (
    CURRENCIES,
    PAYMENT_METHODS,
    RANGE_OPTIONS,
    format_compact,
    format_money,
    resolve_range,
)


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .blueprints.analytics import bp as analytics_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.budgets import bp as budgets_bp
    from .blueprints.categories import bp as categories_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.reports import bp as reports_bp
    from .blueprints.settings import bp as settings_bp
    from .blueprints.transactions import bp as transactions_bp

    for bp in (auth_bp, main_bp, transactions_bp, budgets_bp, categories_bp, analytics_bp, reports_bp, settings_bp):
        app.register_blueprint(bp)

    _register_template_helpers(app)
    _register_errors(app)
    _register_cli(app)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    with app.app_context():
        db.create_all()

    return app


def _register_template_helpers(app):
    def currency_code():
        if current_user.is_authenticated:
            return current_user.currency
        return "INR"

    @app.template_filter("money")
    def money_filter(value, decimals=True, sign=False):
        return format_money(value, currency_code(), decimals=decimals, sign=sign)

    @app.template_filter("compact")
    def compact_filter(value):
        return format_compact(value, currency_code())

    @app.template_filter("tojson_safe")
    def tojson_safe(value):
        def default(o):
            if isinstance(o, Decimal):
                return float(o)
            if isinstance(o, date):
                return o.isoformat()
            raise TypeError
        text = json.dumps(value, default=default)
        for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("'", "\\u0027")):
            text = text.replace(ch, esc)
        return Markup(text)

    @app.template_filter("dt")
    def date_filter(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else ""

    @app.context_processor
    def inject_globals():
        ctx = {
            "currencies": CURRENCIES,
            "range_options": RANGE_OPTIONS,
            "today": date.today(),
        }
        if current_user.is_authenticated and request.endpoint and not request.endpoint.startswith("auth."):
            from .models import Category
            from .services.analytics import budget_status, notifications
            ctx["current_range"] = resolve_range(session.get("range"))
            ctx["currency_symbol"] = CURRENCIES.get(current_user.currency, CURRENCIES["INR"])["symbol"]
            ctx["notifications"] = notifications(current_user.id, current_user.currency)
            ctx["side_budget"] = budget_status(current_user.id)["overall"]
            ctx["all_categories"] = (Category.query.filter_by(user_id=current_user.id)
                                     .order_by(Category.name).all())
            ctx["payment_methods"] = PAYMENT_METHODS
        else:
            ctx.setdefault("notifications", [])
        return ctx


def _register_errors(app):
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404, title="Page not found",
                               message="The page you are looking for doesn't exist or you don't have access to it."), 404

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_template("errors/error.html", code=400, title="Session expired",
                               message="Your form session expired. Please go back, refresh the page and try again."), 400

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500


def _register_cli(app):
    @app.cli.command("seed-demo")
    @click.option("--email", default="demo@finora.app")
    @click.option("--password", default="demo1234")
    def seed_demo(email, password):
        """Create (or reset) a demo account populated with 12 months of data."""
        from .models import User
        from .services.seed import create_default_categories, generate_demo_data

        user = User.query.filter_by(email=email).first()
        if user:
            db.session.delete(user)
            db.session.commit()
        user = User(name="Aarav Sharma", email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        create_default_categories(user)
        generate_demo_data(user)
        click.echo(f"Demo account ready: {email} / {password}")
