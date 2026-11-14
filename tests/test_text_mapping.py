"""Regression checks for text mapped inside styled controls."""
import unittest

from backend.sources import suggestions
from capture import JS_STYLE, normalise
from playwright.sync_api import sync_playwright


class TextMappingTests(unittest.TestCase):
    def test_direct_text_beats_surrounding_button(self):
        frame = {"id": "1:1", "children": [
            {"id": "1:2", "type": "TEXT", "name": "Mobiles", "characters": "Mobiles"}]}
        common = {"text": "Mobiles", "identity": "", "role": "", "label": ""}
        dom = [{**common, "selector": "button", "tag": "button", "direct_text": ""},
               {**common, "selector": "button > span", "tag": "span", "direct_text": "Mobiles"}]
        self.assertEqual(suggestions(frame, dom, 858, {})[0]["selector"], "button > span")

    def test_text_bounds_exclude_control_padding_and_keep_nested_text(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content("""
                    <button style="display:inline-flex;padding:20px;border-radius:8px;
                      color:color(srgb 1 0 0);background:transparent">
                      Shop deals<svg width="20" height="20"></svg>
                    </button>
                    <div style="color:white">Explore <span>Plus</span></div>
                """)
                whole = normalise(page.evaluate(JS_STYLE, "button"))
                text = normalise(page.evaluate(JS_STYLE, {"css": "button", "text_only": True}))
                self.assertLess(text["w"], whole["w"] - 20)
                self.assertEqual(text["color"], "#ff0000")
                nested = normalise(page.evaluate(JS_STYLE, {"css": "div", "text_only": True}))
                explore = page.locator("span").bounding_box()
                self.assertGreaterEqual(nested["x"] + nested["w"], explore["x"] + explore["width"] - .2)
            finally:
                browser.close()
