"""Regression checks for Studio's automatic frame selection and input contract."""
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from uipath import studio_bridge as bridge


class StudioInputTests(unittest.TestCase):
    def arguments(self, directory, node="1-2"):
        return argparse.Namespace(
            mode="figma", widths="auto", workbook=str(Path(directory) / "pages.xlsx"),
            figma=f"https://www.figma.com/design/example/Screen?node-id={node}",
            live="https://example.com", desktop_frame="", mobile_frame="",
        )

    def test_main_prompts_for_two_links(self):
        root = ElementTree.parse(bridge.ROOT / "uipath/DesignQAAutomation/Main.xaml")
        namespace = {"ui": "http://schemas.uipath.com/workflow/activities"}
        prompts = root.findall(".//ui:InputDialog", namespace)
        self.assertEqual([item.attrib["DisplayName"] for item in prompts],
                         ["Enter the Figma design link", "Enter the live website link"])

    def test_auto_uses_selected_858px_frame(self):
        frame = {"id": "1:2", "name": "Screen", "type": "FRAME",
                 "absoluteBoundingBox": {"x": 0, "y": 0, "width": 858, "height": 718}}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bridge, "live_url"),
            patch.object(bridge, "configured_token", return_value="test-credential"),
            patch.object(bridge, "discover", return_value=[
                {"id": "1:2", "name": "Reference", "width": 858},
                {"id": "1:554", "name": "Comparison", "width": 858}]),
            patch.object(bridge, "fetch_frames", return_value=({"1:2": frame}, {"1:2": "export"})),
            patch.object(bridge, "download_image", side_effect=lambda url, path: path.write_bytes(b"fixture")),
            patch.object(bridge, "inspect_dom", return_value=[]),
        ):
            bridge.prepare(self.arguments(directory))
            settings, pages, mapping = bridge.run_qa.load_config(Path(directory) / "pages.xlsx")
            self.assertEqual(pages[0]["Breakpoint"], 858)
            self.assertEqual(settings["MaxRetries"], 0)
            self.assertTrue(settings["AllowVisualOnly"])

    def test_page_link_requires_unambiguous_frame(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bridge, "live_url"),
            patch.object(bridge, "configured_token", return_value="test-credential"),
            patch.object(bridge, "discover", return_value=[
                {"id": "1:2", "width": 858}, {"id": "1:554", "width": 858}]),
        ):
            with self.assertRaisesRegex(bridge.BusinessError, "Copy link to selection"):
                bridge.prepare(self.arguments(directory, "0-1"))

    def test_missing_token_is_actionable(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bridge, "live_url"),
            patch.object(bridge, "configured_token", return_value=""),
        ):
            with self.assertRaisesRegex(bridge.BusinessError, "One-time setup"):
                bridge.prepare(self.arguments(directory))


if __name__ == "__main__":
    unittest.main()

