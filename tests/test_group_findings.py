import unittest

from backend import sources  # Initializes the existing scripts import path.
from group_findings import group_frame_findings


class GroupFindingsTests(unittest.TestCase):
    def test_flow_measurements_are_grouped_and_independent_shift_is_kept(self):
        def node(identifier, path, y, height):
            return {"id": identifier, "path": path, "box": {"y": y, "height": height}}
        reference = {"nodes": [node("frame", "", 0, 800), node("heading", "/0/0", 100, 100),
                               node("sub", "/0/1", 220, 30), node("button", "/0/2", 300, 50)]}
        actual = {"nodes": [node("frame2", "", 0, 800), node("heading2", "/0/0", 120, 50),
                            node("sub2", "/0/1", 190, 30), node("button2", "/0/2", 330, 50)]}
        mapping = [{"label": name, "reference_id": name, "comparison_id": name + "2"}
                   for name in ("heading", "sub", "button")]
        findings = [
            {"label": "heading", "property": "Font size", "expected": "60px", "actual": "36px"},
            {"label": "heading", "property": "Height", "expected": "100px", "actual": "50px"},
            {"label": "heading", "property": "Y position", "expected": "100px", "actual": "120px"},
            {"label": "sub", "property": "Y position", "expected": "220px", "actual": "190px"},
            {"label": "button", "property": "Y position", "expected": "300px", "actual": "330px"},
        ]
        result = group_frame_findings(findings, mapping, reference, actual)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]["related_measurements"]), 3)
        self.assertEqual(result[1]["label"], "button")
        self.assertEqual(len(findings), 5)

    def test_position_only_changes_are_preserved(self):
        source = {"nodes": [{"id": "frame", "box": {"y": 0}}]}
        findings = [{"label": "button", "property": "Y position", "expected": "20px", "actual": "60px"}]
        # A position-only finding has no typography leader and requires no causal grouping.
        result = group_frame_findings(findings, [], source, source)
        self.assertEqual(result[0]["property"], "Y position")
