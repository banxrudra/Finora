"""Database models.

All monetary values are stored as integer minor units (paise / cents) and are
exposed as ``Decimal`` so that no floating point arithmetic touches money.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .utils import from_minor, to_minor


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    theme = db.Column(db.String(10), nullable=False, default="light")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    categories = db.relationship("Category", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return ("".join(p[0] for p in parts[:2]) or self.email[0]).upper()

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else ""


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (db.UniqueConstraint("user_id", "name", "kind", name="uq_category_user_name_kind"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(40), nullable=False)
    kind = db.Column(db.String(7), nullable=False)  # "income" | "expense"
    icon = db.Column(db.String(40), nullable=False, default="tag")
    color = db.Column(db.String(7), nullable=False, default="#2a78d6")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    transactions = db.relationship("Transaction", backref="category", lazy="dynamic")
    budgets = db.relationship("Budget", backref="category", lazy="dynamic", cascade="all, delete-orphan")


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    title = db.Column(db.String(80), nullable=False)
    kind = db.Column(db.String(7), nullable=False)  # "income" | "expense"
    amount_minor = db.Column(db.BigInteger, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    method = db.Column(db.String(20), nullable=False, default="UPI")
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    @property
    def amount(self) -> Decimal:
        return from_minor(self.amount_minor)

    @amount.setter
    def amount(self, value) -> None:
        self.amount_minor = to_minor(value)

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.kind == "income" else -self.amount

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "amount": str(self.amount),
            "date": self.date.isoformat(),
            "method": self.method,
            "notes": self.notes or "",
            "category_id": self.category_id,
        }


class Budget(db.Model):
    """A recurring monthly limit. ``category_id`` NULL means the overall monthly budget."""

    __tablename__ = "budgets"
    __table_args__ = (db.UniqueConstraint("user_id", "category_id", name="uq_budget_user_category"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    amount_minor = db.Column(db.BigInteger, nullable=False)
    alert_threshold = db.Column(db.Integer, nullable=False, default=80)  # percent
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    @property
    def amount(self) -> Decimal:
        return from_minor(self.amount_minor)

    @amount.setter
    def amount(self, value) -> None:
        self.amount_minor = to_minor(value)
