"""Visual QA: log in as the demo user and capture every page at several widths.

Usage:  python scripts/screenshots.py [base_url] [out_dir] [pages...]
Requires the app running and Microsoft Edge or Chrome installed (Playwright channel).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
ONLY = sys.argv[3:]
PAGES = {
    "dashboard": "/dashboard",
    "transactions": "/transactions/",
    "budgets": "/budgets/",
    "categories": "/categories/",
    "analytics": "/analytics/",
    "reports": "/reports/",
    "settings": "/settings/",
}
WIDTHS = {"desktop": (1440, 900), "laptop": (1366, 768), "tablet": (768, 1024), "mobile": (375, 812)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        for theme in ("light", "dark"):
            for label, (w, h) in WIDTHS.items():
                if theme == "dark" and label not in ("desktop", "mobile"):
                    continue
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                          color_scheme=theme)
                page = ctx.new_page()
                page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text}"))
                page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
                if label == "desktop" and theme == "light" and not ONLY:
                    page.goto(BASE + "/login")
                    page.screenshot(path=str(OUT / "login-desktop.png"))
                page.goto(BASE + "/login")
                page.fill("#email", "demo@finora.app")
                page.fill("#password", "demo1234")
                page.click("button[type=submit]")
                page.wait_for_url("**/dashboard")
                if theme == "dark":
                    page.evaluate("window.FinoraApplyTheme('dark')")
                for name, path in PAGES.items():
                    if ONLY and name not in ONLY:
                        continue
                    page.goto(BASE + path)
                    if theme == "dark":
                        page.evaluate("window.FinoraApplyTheme('dark')")
                    page.wait_for_timeout(900)
                    leftover = page.locator("i[data-lucide]").count()
                    if leftover:
                        names = page.eval_on_selector_all("i[data-lucide]", "els => els.map(e => e.dataset.lucide)")
                        problems.append(f"{name}: unrendered icons {sorted(set(names))}")
                    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    if overflow > 0:
                        problems.append(f"{name}@{label}: horizontal overflow {overflow}px")
                    page.screenshot(path=str(OUT / f"{name}-{label}{'-dark' if theme == 'dark' else ''}.png"),
                                    full_page=True)
                ctx.close()
        browser.close()
    print("\n".join(sorted(set(problems))) or "No problems detected")


if __name__ == "__main__":
    main()
