from datetime import date
from decimal import Decimal

from app.config import TestConfig
from app.extensions import db
from app.models import Budget, Category, Transaction, User
from tests.conftest import login, register


def cat(name, kind="expense", email="test@example.com"):
    u = User.query.filter_by(email=email).first()
    return Category.query.filter_by(user_id=u.id, name=name, kind=kind).first()


def add_tx(client, **kw):
    data = {"title": "Lunch", "kind": "expense", "amount": "250.50", "date": date.today().isoformat(),
            "method": "UPI", "category_id": ""}
    data.update(kw)
    return client.post("/transactions/new", data=data)


# ---------------------------------------------------------------- auth
def test_register_creates_hashed_user_and_default_categories(client):
    r = register(client)
    assert r.status_code == 302
    u = User.query.one()
    assert u.password_hash != "password123" and u.check_password("password123")
    assert Category.query.filter_by(user_id=u.id).count() >= 10


def test_register_validation(client):
    r = client.post("/register", data={"name": "A", "email": "bad", "password": "short", "confirm": "x"})
    assert r.status_code == 400
    assert User.query.count() == 0
    register(client)
    client.post("/logout")
    r = register(client)  # duplicate email
    assert r.status_code == 400 and b"already exists" in r.data


def test_login_logout_and_protection(client):
    assert client.get("/dashboard").status_code == 302
    register(client)
    client.post("/logout")
    assert login(client, password="wrong").status_code == 400
    assert login(client).status_code == 302
    assert client.get("/dashboard").status_code == 200
    client.post("/logout")
    assert client.get("/transactions/").status_code == 302


def test_open_redirect_blocked(client):
    register(client)
    client.post("/logout")
    r = client.post("/login?next=https://evil.com", data={"email": "test@example.com", "password": "password123"})
    assert r.headers["Location"].endswith("/dashboard")


# -------------------------------------------------------- transactions
def test_transaction_crud(auth_client):
    food = cat("Food & Dining")
    assert add_tx(auth_client, category_id=food.id).status_code == 302
    t = Transaction.query.one()
    assert t.amount == Decimal("250.50") and t.amount_minor == 25050 and t.category_id == food.id

    auth_client.post(f"/transactions/{t.id}/edit", data={"title": "Dinner", "kind": "expense", "amount": "999.99",
                                                         "date": "2026-01-05", "method": "Cash", "category_id": food.id})
    db.session.refresh(t)
    assert (t.title, t.amount, t.method) == ("Dinner", Decimal("999.99"), "Cash")

    auth_client.post(f"/transactions/{t.id}/delete")
    assert Transaction.query.count() == 0


def test_transaction_validation(auth_client):
    salary = cat("Salary", "income")
    add_tx(auth_client, amount="-5")
    add_tx(auth_client, title="")
    add_tx(auth_client, method="Bitcoin")
    add_tx(auth_client, category_id=salary.id)  # income category on expense
    add_tx(auth_client, date="not-a-date")
    assert Transaction.query.count() == 0


def test_search_filter_and_pagination(auth_client):
    for i in range(15):
        add_tx(auth_client, title=f"Coffee {i}")
    add_tx(auth_client, title="Salary", kind="income", amount="50000")
    r = auth_client.get("/transactions/?q=coffee")
    assert b"Coffee 3" in r.data and b"16 transactions" not in r.data
    r = auth_client.get("/transactions/?kind=income")
    assert b"Salary" in r.data and b"Coffee" not in r.data
    r = auth_client.get("/transactions/?page=2")
    assert r.status_code == 200 and b"of <strong class=\"text-2\">16</strong>" in r.data


# ----------------------------------------------------------- isolation
def test_users_cannot_touch_each_others_data(client):
    register(client, email="a@example.com")
    add_tx(client, title="A secret")
    tx = Transaction.query.one()
    a_cat = cat("Housing", email="a@example.com")
    client.post("/logout")

    register(client, email="b@example.com")
    assert b"A secret" not in client.get("/transactions/").data
    assert client.post(f"/transactions/{tx.id}/edit", data={"title": "hacked"}).status_code == 404
    assert client.post(f"/transactions/{tx.id}/delete").status_code == 404
    assert client.post(f"/categories/{a_cat.id}/delete").status_code == 404
    # cannot attach a transaction to someone else's category
    add_tx(client, category_id=a_cat.id)
    assert Transaction.query.count() == 1
    assert b"A secret" not in client.get("/transactions/export.csv").data
    db.session.refresh(tx)
    assert tx.title == "A secret"


# -------------------------------------------------- budgets & categories
def test_budget_status_and_duplicates(auth_client):
    food = cat("Food & Dining")
    auth_client.post("/budgets/new", data={"category_id": food.id, "amount": "1000", "alert_threshold": "80"})
    auth_client.post("/budgets/new", data={"category_id": food.id, "amount": "2000", "alert_threshold": "80"})
    assert Budget.query.count() == 1
    add_tx(auth_client, amount="1200", category_id=food.id)
    r = auth_client.get("/budgets/")
    assert b"120.0%" in r.data and b"Over by" in r.data
    # overall budget
    auth_client.post("/budgets/new", data={"category_id": "overall", "amount": "50000", "alert_threshold": "90"})
    assert Budget.query.filter_by(category_id=None).count() == 1


def test_category_crud_and_delete_keeps_transactions(auth_client):
    auth_client.post("/categories/new", data={"name": "Pets", "kind": "expense", "icon": "paw-print", "color": "#2a78d6"})
    pets = cat("Pets")
    assert pets is not None
    auth_client.post("/categories/new", data={"name": "pets", "kind": "expense", "icon": "tag", "color": "#2a78d6"})
    assert Category.query.filter(Category.name.ilike("pets")).count() == 1
    auth_client.post("/categories/new", data={"name": "Bad", "kind": "expense", "icon": "<script>", "color": "red"})
    assert cat("Bad") is None
    add_tx(auth_client, category_id=pets.id)
    auth_client.post(f"/categories/{pets.id}/delete")
    assert cat("Pets") is None
    assert Transaction.query.one().category_id is None


# -------------------------------------------------- analytics & reports
def test_dashboard_and_analytics_use_real_data(auth_client):
    add_tx(auth_client, title="Pay", kind="income", amount="80000", category_id=cat("Salary", "income").id)
    add_tx(auth_client, title="Rent", amount="20000", category_id=cat("Housing").id)
    data = auth_client.get("/analytics/data?period=3").get_json()
    assert data["income"][-1] == 80000.0 and data["expense"][-1] == 20000.0
    assert data["savings"][-1] == 60000.0
    assert data["categories"][0]["name"] == "Housing"
    html = auth_client.get("/dashboard").data.decode()
    assert "₹80,000" in html and "₹60,000" in html and "Housing" in html


def test_csv_export_and_formula_injection(auth_client):
    add_tx(auth_client, title="=HYPERLINK(1)")
    r = auth_client.get("/reports/export.csv")
    assert r.mimetype == "text/csv"
    body = r.data.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("Date,Title")
    assert "'=HYPERLINK(1)" in body and "-250.50" in body


def test_demo_data_and_settings(auth_client):
    auth_client.post("/demo-data")
    assert Transaction.query.count() > 100
    auth_client.post("/settings/preferences", data={"currency": "USD", "theme": "dark"})
    u = User.query.one()
    assert (u.currency, u.theme) == ("USD", "dark")
    assert b'data-theme-pref="dark"' in auth_client.get("/dashboard").data
    r = auth_client.post("/settings/theme", json={"theme": "light"})
    assert r.get_json()["ok"] and User.query.one().theme == "light"
    auth_client.post("/settings/password", data={"current": "password123", "new": "newpass456", "confirm": "newpass456"})
    auth_client.post("/logout")
    assert login(auth_client, password="newpass456").status_code == 302


def test_every_page_renders(auth_client):
    auth_client.post("/demo-data")
    for url in ["/dashboard", "/transactions/", "/budgets/", "/categories/", "/categories/?tab=income",
                "/analytics/", "/analytics/?period=12", "/reports/", "/reports/?preset=year",
                "/settings/", "/settings/?tab=preferences", "/settings/?tab=security", "/settings/?tab=data"]:
        assert auth_client.get(url).status_code == 200, url
    for key in ["last_month", "last_3_months", "this_year", "last_12_months"]:
        auth_client.post("/range", data={"range": key})
        assert auth_client.get("/dashboard").status_code == 200, key


def test_csrf_enforced():
    from app import create_app

    class CsrfConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfConfig)
    c = app.test_client()
    r = c.post("/register", data={"name": "X Y", "email": "x@example.com", "password": "password123", "confirm": "password123"})
    assert r.status_code == 400
    with app.app_context():
        assert User.query.count() == 0
