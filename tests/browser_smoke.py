"""Browser smoke test against a running DesignQA server."""
import os
import unittest

from playwright.sync_api import expect, sync_playwright


class BrowserTest(unittest.TestCase):
    def test_demo_from_form_to_download(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(os.getenv("DESIGNQA_TEST_URL", "http://127.0.0.1:8000"))
            page.get_by_role("link", name="New analysis", exact=True).last.click()
            page.get_by_role("button", name="Demo analysis").click()
            page.get_by_role("button", name="Analyze website").click()
            expect(page.get_by_role("heading", name="Analysis results")).to_be_visible(timeout=60000)
            expect(page.get_by_role("cell", name="Font size", exact=True)).to_be_visible()
            page.get_by_label("Page and breakpoint").select_option("1")
            expect(page.get_by_role("cell", name="Font size", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Visual comparison").click()
            expect(page.get_by_alt_text("diff screenshot")).to_be_visible()
            page.get_by_role("button", name="Overlay", exact=True).click()
            expect(page.get_by_alt_text("Live screenshot overlay")).to_be_visible()
            with page.expect_download() as download:
                page.get_by_role("link", name="XLSX").click()
            self.assertTrue(download.value.suggested_filename.endswith(".xlsx"))
            page.get_by_role("link", name="History", exact=True).first.click()
            expect(page.get_by_role("link", name="Brewly demo", exact=False).first).to_be_visible()
            page.set_viewport_size({"width": 375, "height": 812})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth === window.innerWidth"))
            self.assertEqual(errors, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
