"""Background worker that adapts web requests to the existing workbook engine."""
import json
import re
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook
from scripts import run_qa
from capture import capture
from demo.make_demo import MAPPING
from figma_client import download_image, extract_tokens
from .sources import (discover, fetch_frames, guard_page,
                      inspect_dom, live_url, suggestions, walk)

ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED = "Line height, border colour, spacing and unexpected elements are unverified."
RECOMMENDATIONS = {
    "Missing": "Check the approved selector and confirm that the component is rendered at this width.",
    "Layout": "Inspect container sizing, responsive rules and positioning against the selected frame.",
    "Style": "Compare the live computed rule with the corresponding design property.",
    "Visual": "Review highlighted areas and confirm fonts, dynamic content and frame dimensions.",
    "Setup": "Review the selected frame and the approved element mapping.",
}


def scope(job, breakpoint, frame):
    return json.dumps([job["file_key"], job["live_url"], breakpoint, frame])


def prepare(job, session, store, stage):
    stage("figma")
    if "frames" not in session:
        session["frames"] = discover(job["file_key"], job.get("preferred"), session["token"])
    if "selected" not in session:
        selected = {}
        if job.get("preferred"):
            frame = next((f for f in session["frames"] if f["id"] == job["preferred"]), None)
            if frame and frame["width"] in job["breakpoints"]:
                selected[frame["width"]] = frame["id"]
        job["selected_frames"] = selected
        if len(selected) != len(job["breakpoints"]):
            job.update(state="awaiting_frames", frames=session["frames"])
            return
        session["selected"] = selected

    selected = session["selected"]
    if "documents" not in session:
        session["documents"], session["exports"] = fetch_frames(job["file_key"], list(selected.values()), session["token"])
    stage("mapping")
    if "proposals" not in session:
        proposals = []
        for width, frame_id in selected.items():
            dom = inspect_dom(job["live_url"], width)
            saved = store.mapping(scope(job, width, frame_id))
            proposals.extend(suggestions(session["documents"][frame_id], dom, width, saved))
        session["proposals"] = proposals
    if "approved" not in session and session["proposals"]:
        job.update(state="awaiting_mapping", mappings=session["proposals"])
        return
    approved = session.get("approved", {})
    for width, frame_id in selected.items():
        proposals = [row for row in session["proposals"] if row["breakpoint"] == width]
        applied = [(row, approved.get((width, row["node_id"]))) for row in proposals]
        applied = [(row, selector) for row, selector in applied if selector]
        if not applied:
            continue
        counts = inspect_dom(job["live_url"], width, [selector for _, selector in applied])
        invalid = [
            row["label"] for (row, selector), count in zip(applied, counts)
            if count != 1 and not (count == 0 and row["confidence"] == "Previously approved" and selector == row["selector"])
        ]
        if invalid:
            session.pop("approved", None)
            job.update(state="awaiting_mapping", mappings=session["proposals"],
                       error={"message": "Selectors must match exactly one element: " + ", ".join(invalid[:5])})
            return
    for width, frame_id in selected.items():
        store.mapping(scope(job, width, frame_id),
                      {node: css for (bp, node), css in approved.items() if bp == width and css})


def write_config(path, pages, mappings, hide, *, retries=1):
    book = Workbook()
    page = book.active
    page.title = "Pages"
    page.append(["Enabled", "PageName", "Breakpoint", "LiveURL", "Threshold", "DesignImage", "DesignStyles", "ViewportHeight"])
    for row in pages:
        page.append(row)
    mapping = book.create_sheet("Mapping")
    mapping.append(["PageName", "Breakpoint", "Label", "FigmaNodeId", "CssSelector", "TextOnly"])
    for row in mappings:
        mapping.append(row)
        for cell in mapping[mapping.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    settings = book.create_sheet("Settings")
    settings.append(["Key", "Value"])
    for key, value in (("AllowVisualOnly", True), ("TimeoutMs", 15000), ("MaxRetries", retries), ("HideSelectors", ",".join(hide))):
        settings.append([key, value])
    book.save(path)
    book.close()


def difference(finding):
    def number(value):
        return re.fullmatch(r"(-?\d+(?:\.\d+)?)(px)?", value)
    expected, actual = number(finding["expected"]), number(finding["actual"])
    if expected and actual and expected[2] == actual[2]:
        return f"{float(actual[1]) - float(expected[1]):+g}{actual[2] or ''}"
    if all(re.fullmatch(r"#[0-9a-fA-F]{6}", finding[k]) for k in ("expected", "actual")):
        from common import color_distance
        return f"RGB channel delta {color_distance(finding['expected'], finding['actual'])}"
    return None


def analyze(job, session, root, stage, save):
    run = root / job["job_id"]
    run.mkdir(exist_ok=True)
    demo = job["mode"] == "demo"
    coverage = {}
    with TemporaryDirectory(prefix="designqa-input-") as temp:
        temp = Path(temp)
        pages, mappings = [], []
        for width in job["breakpoints"]:
            png, tokens = temp / f"{width}.png", temp / f"{width}.json"
            if demo:
                stage("figma", "Capturing the local Brewly reference.")
                baseline = ROOT / "demo/site/good/index.html"
                source = ROOT / ("demo/site/buggy/index.html" if job["demo_variant"] == "buggy" else "demo/site/good/index.html")
                name = "Brewly"
                reference = capture(baseline.as_uri(), width, png, [{"label": label, "css": css} for label, _, css in MAPPING])
                mappings.extend([name, width, label, node, css] for label, node, css in MAPPING)
                coverage[width] = ["8 fixture elements mapped.", UNSUPPORTED]
                stage("mapping", "Loaded the fixture selectors.")
            else:
                stage("figma")
                frame_id = session["selected"][width]
                frame = session["documents"][frame_id]
                download_image(session["exports"][frame_id], png)
                name, source = "Website", job["live_url"]
                reference = {}
                nodes = {node["id"]: node for node in walk(frame)}
                approved = session.get("approved", {})
                for row in session["proposals"]:
                    if row["breakpoint"] != width or not (css := approved.get((width, row["node_id"]))):
                        continue
                    label = f"{row['label']} [{row['node_id']}]"
                    reference[label] = extract_tokens(nodes[row["node_id"]], frame["absoluteBoundingBox"])
                    mappings.append([name, width, label, row["node_id"], css, nodes[row["node_id"]]["type"] == "TEXT"])
                total = sum(row["breakpoint"] == width for row in session["proposals"])
                coverage[width] = [f"{len(reference)} of {total} candidate layers mapped. Unmapped layers and unavailable properties are unverified.",
                                   f"Figma frame {frame['name']} ({frame_id}), {frame['absoluteBoundingBox']['width']:g} px wide.", UNSUPPORTED]
            tokens.write_text(json.dumps(reference), encoding="utf-8")
            pages.append(["Y", name, width, str(source), 0.97, str(png), str(tokens)])
        workbook = temp / "job.xlsx"
        write_config(workbook, pages, mappings, job["hide_selectors"])
        settings, rows, maprows = run_qa.load_config(workbook)
        checks = []
        for row in rows:
            def notify(key):
                stage(key, f"{row['Breakpoint']} px")

            capture_page = capture if demo else partial(capture, page_setup=guard_page)
            result = run_qa.process_row(row, settings, maprows, run, notify=notify, capture_page=capture_page)
            result["url"] = job["live_url"] or f"Brewly demo ({job['demo_variant']})"
            if result["status"] == "ERROR":
                result["error"] = "The browser or comparison could not complete this breakpoint."
            result["coverage"] = coverage[result["breakpoint"]]
            for finding in result["findings"]:
                finding["difference"] = difference(finding)
                finding["recommendation"] = RECOMMENDATIONS.get(finding["category"], "Review the comparison evidence.")
            (run / "rows" / f"{row['_row']}.json").write_text(json.dumps(result), encoding="utf-8")
            checks.append(result)
            job["completed_checks"] = len(checks)
            save(job)

    stage("report")
    provenance = {"Website": job["live_url"] or "Brewly demo", "Figma": job["figma_url"] or "Local reference",
                  "Started": job["created_at"]}
    from report import build_html, build_xlsx
    build_html(checks, run, run / "report.html", job["job_id"], provenance=provenance)
    build_xlsx(checks, run / "findings.xlsx", provenance=provenance)
    scores = [row["ssim"] for row in checks if row.get("ssim") is not None]
    result = {"job_id": job["job_id"], "live_url": provenance["Website"], "figma_url": job["figma_url"],
              "created_at": job["created_at"], "checks": checks,
              "similarity": sum(scores) / len(scores) if scores else None,
              "issues": sum(len(row["findings"]) for row in checks)}
    for check in checks:
        if "images" in check:
            check["images"] = {key: f"/api/results/{job['job_id']}/images/{Path(value).name}"
                               for key, value in check["images"].items()}
    verdicts = {row["status"] for row in checks}
    result["verdict"] = "ERROR" if verdicts == {"ERROR"} else "PARTIAL" if "ERROR" in verdicts else "FAIL" if "FAIL" in verdicts else "PASS"
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    job.update(state="completed", verdict=result["verdict"], similarity=result["similarity"], issues=result["issues"])

