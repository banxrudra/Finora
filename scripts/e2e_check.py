"""End-to-end interaction check in a real browser (Edge via Playwright).

Usage: python scripts/e2e_check.py [base_url]
Creates a throwaway user, exercises every interactive flow, then deletes the account.
"""
import sys
import time

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
EMAIL = f"e2e{int(time.time())}@example.com"
results = []


def step(name, fn):
    try:
        fn()
        results.append(("PASS", name))
    except Exception as e:  # noqa: BLE001
        results.append(("FAIL", f"{name}: {str(e).splitlines()[0][:160]}"))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        ctx = browser.new_context(viewport={"width": 1366, "height": 860}, accept_downloads=True)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def register():
            page.goto(BASE + "/register")
            page.fill("#name", "Priya Nair")
            page.fill("#email", EMAIL)
            page.fill("#password", "secret123")
            page.fill("#confirm", "secret123")
            page.click("button[type=submit]")
            page.wait_for_url("**/dashboard")
            expect(page.locator(".welcome")).to_be_visible()
        step("register + empty-state dashboard", register)

        def add_tx():
            page.click(".topbar__actions [data-modal-open=tx-modal]")
            expect(page.locator("#tx-modal")).to_be_visible()
            page.fill("#tx-title", "Team lunch")
            page.fill("#tx-amount", "1234.50")
            page.select_option("#tx-category", label="Food & Dining")
            page.click("#tx-modal button[type=submit]")
            page.wait_for_load_state()
            expect(page.locator(".toast")).to_contain_text("Team lunch")
        step("add expense via modal", add_tx)

        def income_filters_categories():
            page.click(".topbar__actions [data-modal-open=tx-modal]")
            page.click("label[for=tx-kind-income]")
            hidden = page.eval_on_selector("#tx-category optgroup[data-kind=expense]", "g => g.hidden")
            assert hidden, "expense categories should hide for income"
            page.fill("#tx-title", "Freelance invoice")
            page.fill("#tx-amount", "40000")
            page.select_option("#tx-category", label="Freelance")
            page.click("#tx-modal button[type=submit]")
            page.wait_for_load_state()
        step("income modal filters categories by type", income_filters_categories)

        def dashboard_numbers():
            page.goto(BASE + "/dashboard")
            text = page.locator(".grid-4").inner_text()
            assert "₹40,000" in text and "₹1,234" in text and "₹38,765" in text, text
        step("dashboard KPIs reflect DB", dashboard_numbers)

        def edit_tx():
            page.goto(BASE + "/transactions/")
            row = page.locator("tr", has_text="Team lunch")
            row.locator("[data-modal-open]").click()
            expect(page.locator("#tx-title")).to_have_value("Team lunch")
            expect(page.locator("#tx-amount")).to_have_value("1234.50")
            page.fill("#tx-title", "Team dinner")
            page.click("#tx-modal button[type=submit]")
            page.wait_for_load_state()
            expect(page.locator("tbody")).to_contain_text("Team dinner")
        step("edit transaction (modal prefilled)", edit_tx)

        def search_filter():
            page.fill("input[name=q]", "dinner")
            page.wait_for_url("**q=dinner**")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.goto(BASE + "/transactions/?kind=income")
            expect(page.locator("tbody")).to_contain_text("Freelance invoice")
            expect(page.locator("tbody")).not_to_contain_text("Team dinner")
            page.click("[data-toggle=filter-panel]")
            expect(page.locator("#filter-panel")).to_be_visible()
        step("search + type filter + filter panel", search_filter)

        def delete_tx():
            page.goto(BASE + "/transactions/")
            page.locator("tr", has_text="Team dinner").locator("[data-confirm]").click()
            expect(page.locator("#confirm-modal")).to_be_visible()
            page.click("#confirm-modal [data-confirm-btn]")
            page.wait_for_load_state()
            expect(page.locator("tbody")).not_to_contain_text("Team dinner")
        step("delete via confirm dialog", delete_tx)

        def sample_data():
            page.goto(BASE + "/dashboard")
            # account not empty now -> welcome hidden; use a fresh check of transactions count instead
            page.goto(BASE + "/transactions/")
            assert "1 transaction" in page.locator(".page-head p").inner_text()
        step("transaction count after delete", sample_data)

        def budget():
            page.goto(BASE + "/budgets/")
            page.click(".page-head [data-modal-open=budget-modal]")
            page.select_option("#b-cat", label="Overall – all expenses")
            page.fill("#b-amount", "50000")
            page.click("#budget-modal button[type=submit]")
            page.wait_for_load_state()
            expect(page.locator(".overall-card")).to_contain_text("₹50,000.00")
            page.click(".add-tile")
            disabled = page.eval_on_selector("#b-cat option[value=overall]", "o => o.disabled")
            assert disabled, "overall should be disabled once it has a budget"
            page.select_option("#b-cat", label="Shopping")
            page.fill("#b-amount", "100")
            page.click("#budget-modal button[type=submit]")
            page.wait_for_load_state()
            expect(page.locator(".budget-card", has_text="Shopping")).to_be_visible()
        step("create overall + category budget", budget)

        def category():
            page.goto(BASE + "/categories/")
            page.click(".page-head [data-modal-open=cat-modal]")
            page.fill("#c-name", "Pets")
            page.click("label[for=ic-paw-print]")
            page.click("label[for=col-3]")
            expect(page.locator("[data-preview-name]")).to_have_text("Pets")
            page.click("#cat-modal button[type=submit]")
            page.wait_for_load_state()
            expect(page.locator(".cat-card", has_text="Pets")).to_be_visible()
        step("create category with icon/colour picker", category)

        def theme():
            page.goto(BASE + "/dashboard")
            page.click("[data-theme-toggle]")
            assert page.evaluate("document.documentElement.dataset.theme") == "dark"
            page.wait_for_timeout(400)
            page.reload()
            assert page.evaluate("document.documentElement.dataset.theme") == "dark", "theme not persisted"
            page.click("[data-theme-toggle]")
            page.wait_for_timeout(400)
        step("theme toggle persists across reload", theme)

        def range_and_menus():
            page.click(".range-btn")
            page.click("button[name=range][value=last_6_months]")
            page.wait_for_load_state()
            expect(page.locator(".range-btn")).to_contain_text("Last 6 months")
            page.click(".topbar__actions .icon-btn[aria-label^=Notifications]")
            expect(page.locator(".menu-wide")).to_be_visible()
            page.keyboard.press("Escape")
            page.click(".topbar__actions .avatar")
            expect(page.locator(".menu-head")).to_contain_text("Priya Nair")
        step("date range + notification + avatar menus", range_and_menus)

        def exports():
            page.goto(BASE + "/reports/?preset=year")
            with page.expect_download() as d:
                page.click("a[href*='reports/export.csv']")
            content = open(d.value.path(), encoding="utf-8-sig").read()
            assert "Freelance invoice" in content, content[:200]
        step("report CSV download", exports)

        def analytics_charts():
            page.goto(BASE + "/analytics/?period=12")
            page.wait_for_timeout(600)
            n = page.evaluate("Object.keys(Chart.instances).length")
            canvases = page.locator("canvas[data-chart]").count()
            assert n == canvases and n >= 4, f"{n} charts for {canvases} canvases"
        step("analytics mounts a chart on every canvas", analytics_charts)

        def settings():
            page.goto(BASE + "/settings/?tab=preferences")
            page.select_option("#s-cur", "USD")
            page.click("button:has-text('Save preferences')")
            page.wait_for_load_state()
            page.goto(BASE + "/dashboard")
            assert "$" in page.locator(".grid-4").inner_text()
            page.goto(BASE + "/settings/?tab=preferences")
            page.select_option("#s-cur", "INR")
            page.click("button:has-text('Save preferences')")
            page.wait_for_load_state()
        step("currency preference applies", settings)

        def mobile_nav():
            m = browser.new_context(viewport={"width": 375, "height": 812}, storage_state=ctx.storage_state())
            mp = m.new_page()
            mp.goto(BASE + "/dashboard")
            mp.click(".topbar__menu")
            mp.wait_for_timeout(350)
            box = mp.locator(".sidebar").bounding_box()
            assert box["x"] >= -1, f"sidebar not open: {box}"
            mp.click(".scrim", position={"x": 340, "y": 400})
            mp.wait_for_timeout(350)
            assert mp.locator(".sidebar").bounding_box()["x"] < -100
            m.close()
        step("mobile nav opens/closes", mobile_nav)

        def delete_account():
            page.goto(BASE + "/settings/?tab=data")
            page.fill("#d-pass", "secret123")
            page.click("button:has-text('Delete my account')")
            page.wait_for_url("**/login")
            page.fill("#email", EMAIL)
            page.fill("#password", "secret123")
            page.click("button[type=submit]")
            expect(page.locator(".form-alert")).to_be_visible()
        step("delete account + logout", delete_account)

        if errors:
            results.append(("FAIL", "JS errors: " + "; ".join(errors[:3])))
        browser.close()

    for status, name in results:
        print(f"[{status}] {name}")
    sys.exit(any(s == "FAIL" for s, _ in results))


if __name__ == "__main__":
    main()
