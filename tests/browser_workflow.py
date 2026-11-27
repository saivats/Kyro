"""Run with Python Playwright and Chromium installed, from the repository root."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import os
import sys

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import create_demo_app


def exercise(page, url):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(url)
    expect(page.get_by_text("● System ready")).to_be_visible()
    page.get_by_role("link", name="Doctor workspace").click()
    doctor = page.locator("#doctors article").filter(has_text="Demo doctor B")
    doctor.get_by_role("button", name="Edit doctor").click()
    page.get_by_label("Maximum capacity").fill("1")
    page.get_by_role("button", name="Save doctor").click()
    expect(page.locator("#doctor-dialog")).not_to_be_visible()

    for name, review in [("Slot holder","Medium"),("Earlier waiting","Low"),("Priority waiting","Critical")]:
        page.get_by_role("link", name="Case intake").click()
        page.get_by_label("Load preset").select_option("cardiac")
        page.get_by_label("Case label").fill(name)
        page.get_by_label("I confirm that this case is fictional.").check()
        page.get_by_role("button", name="Run AI triage").click()
        modal = page.locator("#inspector")
        expect(modal).to_be_visible()
        expect(modal.get_by_role("heading", name="Top model contributions")).to_be_visible()
        expect(modal.get_by_role("progressbar")).to_have_count(9)
        expect(modal.get_by_text("Fictional chest discomfort",exact=True)).to_be_visible()
        modal.get_by_label("Confirmed severity").select_option(label=review)
        modal.get_by_role("button", name="Confirm review").click()
        expect(modal).not_to_be_visible()
    row = lambda name: page.locator("#rows tr").filter(has_text=name)
    expect(row("Earlier waiting")).to_contain_text("Waiting")
    expect(row("Priority waiting")).to_contain_text("Waiting")
    row("Slot holder").get_by_role("button", name="Start treatment").click()
    row("Slot holder").get_by_role("button", name="Complete treatment").click()
    expect(row("Priority waiting")).to_contain_text("Demo doctor B")
    expect(row("Earlier waiting")).to_contain_text("Waiting")
    page.reload()
    expect(row("Priority waiting")).to_contain_text("Demo doctor B")
    page.get_by_label("Workflow state").select_option("completed")
    expect(row("Slot holder")).to_contain_text("Completed")
    page.get_by_role("link", name="Model report").click()
    expect(page.get_by_role("heading", name="Historical confusion matrix")).to_be_visible()
    page.get_by_role("link", name="Activity", exact=True).click()
    expect(page.locator("#events")).to_contain_text("Priority waiting")
    page.set_viewport_size({"width":390,"height":844})
    page.get_by_role("link", name="Overview", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors


if __name__ == "__main__":
    with TemporaryDirectory() as temp, sync_playwright() as pw:
        server = make_server("127.0.0.1",0,create_demo_app(Path(temp)/"browser.db"),threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            browser = pw.chromium.launch(channel=os.getenv("KYRO_BROWSER_CHANNEL"))
            try:
                exercise(browser.new_page(), f"http://127.0.0.1:{server.server_port}")
            finally:
                browser.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
    print("Browser workflow passed with real model, persistence and priority dispatch.")
