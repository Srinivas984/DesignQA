import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app import create_app
from backend.sources import BusinessError, SystemFault, figma_url, live_url, suggestions
from figma_client import download_image


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = self.enterContext(TestClient(create_app(self.temp.name)))

    def test_validation_and_network_error(self):
        self.assertEqual(figma_url("https://www.figma.com/design/abc123/Landing?node-id=12-34"), ("abc123", "12:34"))
        data = {"mode": "figma", "breakpoints": [1440], "figma_url": "https://figma.com/design/sample", "live_url": "https://example.com"}
        with patch.dict(os.environ, {"FIGMA_TOKEN": ""}):
            self.assertIn("token", self.client.post("/api/analyze", json=data).json()["detail"])
        self.assertEqual(self.client.post("/api/analyze", json={**data, "figma_url": "https://example.com/design/test"}).status_code, 422)
        self.assertEqual(self.client.post("/api/analyze", json={**data, "live_url": "http://127.0.0.1/"}).status_code, 422)
        with patch("backend.sources.socket.getaddrinfo", side_effect=__import__("socket").gaierror):
            with self.assertRaises(SystemFault):
                live_url(data["live_url"], resolve=True)
            payload = {**data, "figma_token": "temporary-test-token"}
            response = self.client.post("/api/analyze", json=payload)
            self.assertEqual(response.status_code, 202)
            state = self.wait(response.json()["job_id"])
            self.assertEqual(state["state"], "failed")
            self.assertEqual(state["error"]["type"], "SystemFault")
            self.assertNotIn(b"temporary-test-token", (Path(self.temp.name) / "workspace.sqlite3").read_bytes())

    def wait(self, job_id):
        for _ in range(240):
            job = self.client.get(f"/api/analyze/{job_id}").json()
            if job["state"] not in ("queued", "running"):
                return job
            time.sleep(.25)
        self.fail("Analysis did not finish in 60 seconds.")

    def test_real_demo_and_reports(self):
        expected = {("Hero heading", "Font size"), ("Hero subtitle", "Y position"),
                    ("Promo badge", "Element"), ("CTA button", "Background colour"),
                    ("Feature card 1", "Corner radius")}
        for variant in ("baseline", "buggy"):
            with self.subTest(variant=variant):
                response = self.client.post("/api/analyze", json={"mode": "demo", "demo_variant": variant, "breakpoints": [1440, 375]})
                self.assertEqual(response.status_code, 202)
                job_id = response.json()["job_id"]
                state = self.wait(job_id)
                self.assertEqual(state["state"], "completed", state)
                self.assertEqual(state["completed_checks"], 2)
                self.assertTrue({"validate", "figma", "mapping", "capture", "visual", "styles", "report"} <= {e["stage"] for e in state["events"]})
                result = self.client.get(f"/api/results/{job_id}").json()
                for check in result["checks"]:
                    if variant == "baseline":
                        self.assertEqual((check["status"], check["ssim"], check["findings"]), ("PASS", 1.0, []))
                    else:
                        observed = {(f["label"], f["property"]) for f in check["findings"]}
                        active = expected if check["breakpoint"] == 1440 else expected - {("Hero heading", "Font size")}
                        self.assertEqual(observed & expected, active)
                    for image in check["images"].values():
                        self.assertTrue(self.client.get(image).content.startswith(b"\x89PNG"))
                base = f"/api/reports/{job_id}"
                self.assertIn(b"data:image/jpeg;base64,", self.client.get(base).content)
                excel = load_workbook(io.BytesIO(self.client.get(base + "?format=xlsx").content))
                self.assertEqual(excel.sheetnames, ["Findings", "Summary", "Analysis"])
                excel.close()
                self.assertEqual(self.client.get(base + "?format=json").json(), result)
                self.assertEqual(self.client.get(f"/api/results/{job_id}/images/unlisted.png").status_code, 404)
        self.assertEqual(self.client.get("/api/history").json()["total"], 2)

    def test_frame_and_mapping_review(self):
        frames = [{"id": "1:1", "name": "Desktop", "width": 1440, "height": 900}]
        frame = {"id": "1:1", "children": [{
            "id": "1:2", "name": "Hero heading", "type": "TEXT", "characters": "Welcome",
        }]}
        dom = [{"tag": "h1", "text": "Welcome", "selector": "#hero", "identity": "hero", "role": "", "label": ""}]
        data = {"mode": "figma", "breakpoints": [1440], "figma_url": "https://figma.com/design/sample",
                "live_url": "https://example.com", "figma_token": "review-test-token"}

        def inspect(url, width, selectors=()):
            return [1 if selector == "#hero" else 2 for selector in selectors] if selectors else dom

        def finish(job, session, root, stage, save):
            job.update(state="completed", verdict="PASS", similarity=1, issues=0)

        with (
            patch("backend.app.live_url", side_effect=lambda url, **kwargs: url),
            patch("backend.worker.discover", return_value=frames),
            patch("backend.worker.fetch_frames", return_value=({"1:1": frame}, {})),
            patch("backend.worker.inspect_dom", side_effect=inspect),
            patch("backend.app.analyze", side_effect=finish),
        ):
            response = self.client.post("/api/analyze", json=data)
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["job_id"]
            endpoint = f"/api/analyze/{job_id}"
            self.assertEqual(self.wait(job_id)["state"], "awaiting_frames")
            self.assertEqual(self.client.post(endpoint + "/frames", json={"frames": [{"breakpoint": 1440, "frame_id": "1:1"}]}).status_code, 202)
            state = self.wait(job_id)
            self.assertEqual(state["state"], "awaiting_mapping")
            self.assertEqual(state["mappings"][0]["selector"], "#hero")
            review = {"mappings": [{"breakpoint": 1440, "node_id": "1:2", "selector": "h1"}]}
            self.assertEqual(self.client.post(endpoint + "/mapping", json=review).status_code, 202)
            self.assertIn("exactly one", self.wait(job_id)["error"]["message"])
            review["mappings"][0]["selector"] = "#hero"
            self.assertEqual(self.client.post(endpoint + "/mapping", json=review).status_code, 202)
            self.assertEqual(self.wait(job_id)["state"], "completed")
            self.assertEqual(self.client.app.state.store.mapping('["sample", "https://example.com", 1440, "1:1"]'), {"1:2": "#hero"})

    def test_mapping_confidence_and_export_credentials(self):
        frame = {"id": "1:1", "children": [{"id": "1:2", "name": "Hero heading", "type": "TEXT", "characters": "Welcome"}]}
        item = {"tag": "h1", "text": "Welcome", "selector": "#hero", "identity": "hero", "role": "", "label": ""}
        self.assertEqual(suggestions(frame, [item], 1440, {})[0]["confidence"], "High")
        self.assertEqual(suggestions(frame, [item, {**item, "selector": "#other"}], 1440, {})[0]["confidence"], "Ambiguous")
        self.assertEqual(suggestions(frame, [], 1440, {"1:2": "#saved"})[0]["selector"], "#saved")
        with patch("figma_client.requests.get") as request:
            response = MagicMock(status_code=200)
            response.iter_content.return_value = [b"contents"]
            request.return_value.__enter__.return_value = response
            path = Path(self.temp.name) / "export.png"
            download_image("https://figma-alpha-api.s3.us-west-2.amazonaws.com/image", path)
            self.assertEqual(path.read_bytes(), b"contents")
            self.assertNotIn("headers", request.call_args.kwargs)
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
            with self.assertRaises(BusinessError):
                download_image("https://example.com/image", path)


if __name__ == "__main__":
    unittest.main()

