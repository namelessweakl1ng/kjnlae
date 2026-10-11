"""Optional real-browser smoke against the default loopback development server.

Install Playwright separately. Set KJNLAE_BROWSER_EXECUTABLE to use an installed Chromium.
No model, external account or live tool effect is used.
"""

import os

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    executable = os.getenv("KJNLAE_BROWSER_EXECUTABLE")
    browser = playwright.chromium.launch(executable_path=executable, headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8000")
    page.get_by_text("API connected", exact=True).wait_for()
    page.get_by_role("button", name="Inspect content").click()
    page.get_by_text("BLOCK", exact=True).wait_for()
    assert page.locator("mark").count() > 0
    page.get_by_role("button", name="Attack laboratory", exact=False).first.click()
    page.get_by_text("detector bypass", exact=True).wait_for()
    assert page.get_by_text("Action prevented", exact=True).count() == 4
    page.get_by_role("button", name="Evaluation", exact=False).first.click()
    page.get_by_role("heading", name="Detector comparison").wait_for()
    page.get_by_role("button", name="History", exact=False).first.click()
    page.get_by_role("heading", name="Recent inspections").wait_for()
    page.get_by_role("button", name="Status", exact=False).first.click()
    page.get_by_role("heading", name="Runtime capabilities").wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Scanner", exact=False).first.click()
    assert page.get_by_label("API credential (session only)").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_label("Untrusted content").fill('<img src=x onerror="alert(1)">')
    page.get_by_role("button", name="Inspect content").click()
    page.get_by_text("ALLOW", exact=True).wait_for()
    assert page.locator(".evidence img").count() == 0
    browser.close()
    print(
        "Live browser scan, laboratory, evaluation, history/status, "
        "mobile and HTML rendering passed"
    )
