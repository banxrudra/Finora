# Finora — Personal Finance & Expense Analytics

A personal finance dashboard built with Flask. Track income and expenses, set monthly budgets that warn you before you overspend, and see where your money goes in charts and printable reports.

![Dashboard](docs/screenshots/dashboard-desktop.png)

| Dark mode | Mobile |
|---|---|
| ![Dark](docs/screenshots/dashboard-desktop-dark.png) | ![Mobile](docs/screenshots/transactions-mobile.png) |

## Features

- **Dashboard**: balance, income, expense and savings KPIs with sparklines and period-over-period change. Also shows income vs expenses, spending by category, a cumulative spending trend, budget progress, recent transactions and automatic insights.
- **Transactions**: search, filters (type, category, payment method, date range), sorting and pagination. Add and edit in a modal, delete with confirmation, and export the filtered list to CSV.
- **Budgets**: an overall monthly budget plus one per category, each with an adjustable alert threshold. Warning and over-budget states, and a month-by-month history.
- **Categories**: custom income and expense categories with an icon and colour picker. Deleting a category keeps its transactions; they become uncategorised.
- **Analytics** (Chart.js, all from the database): income vs expenses, category doughnut, spending trend with 3-month average, monthly savings, and budget vs actual.
- **Reports**: presets or a custom date range, summary stats, category breakdowns, largest expenses, a monthly table, CSV export and a print stylesheet (Print / PDF).
- **Settings**: profile, currency (INR with Indian digit grouping, USD, EUR, GBP), light/dark/system theme, password change, data export and account deletion.
- **Notifications**: budget threshold alerts and unusually large recent expenses.
- **Responsive**: tested at 1440, 1366, 768 and 375 px, with an off-canvas sidebar on mobile.

## Engineering notes

- **Money is never a float.** Amounts are stored as integer paise (`BIGINT`) and exposed as `Decimal`. Input is parsed strictly: it must be positive, have at most 2 decimal places, and be finite.
- **User data isolation.** Every query is scoped by `user_id`. Fetching a record by id goes through `owned()`, which returns 404 (not 403) for another user's record. Category ids sent in forms are checked for ownership and type.
- **Security.** Passwords are hashed with Werkzeug scrypt. CSRF protection (Flask-WTF) covers every form and the fetch call. The session is cleared on login and logout. `next` redirects are restricted to the same site. CSV export guards against spreadsheet formula injection. Cookies are HttpOnly and SameSite, and standard security headers are set. The secret key comes from an environment variable.
- **Architecture.** An app factory with blueprints (`auth`, `main`, `transactions`, `budgets`, `categories`, `analytics`, `reports`, `settings`). All aggregation lives in `app/services/analytics.py`.

```
app/
  __init__.py          app factory, filters, context, CLI
  models.py            User, Category, Transaction, Budget
  utils.py             money / date helpers, INR formatting
  services/            analytics aggregation, demo seeding
  blueprints/          route modules
  templates/           Jinja2 (base shell, pages, partials)
  static/css/app.css   design system (tokens, light + dark)
  static/js/           app.js (UI), charts.js (Chart.js theming)
tests/                 pytest suite
scripts/               screenshot + end-to-end browser checks
```

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set SECRET_KEY

flask --app run.py seed-demo    # optional: demo@finora.app / demo1234 with 12 months of data
python run.py                   # http://127.0.0.1:5000
```

New accounts start with a set of default categories and offer one-click **Load sample data** on the dashboard.

## Tests

```bash
pytest                                   # unit + integration tests
pip install playwright                   # optional browser checks (uses installed Edge)
python scripts/e2e_check.py              # clicks through every interactive flow
python scripts/screenshots.py            # regenerates docs/screenshots at 4 widths + dark
```

## Tech stack

Python · Flask · Flask-SQLAlchemy · Flask-Login · Flask-WTF · SQLite · Jinja2 · vanilla JS · Chart.js · Lucide icons · Inter
