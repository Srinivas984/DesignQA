"""Compare two exported Figma frames using their measured node properties."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_styles import compare
from diff import visual_diff
from report import build_html, build_xlsx
from group_findings import group_frame_findings


def tokens(node, frame):
    box, origin = node["box"], frame["nodes"][0]["box"]
    font = node.get("fontName") or {}
    return {
        "x": round(box["x"] - origin["x"], 2), "y": round(box["y"] - origin["y"], 2),
        "w": round(box["width"], 2), "h": round(box["height"], 2),
        "fontFamily": font.get("family"), "fontSize": node.get("fontSize"),
        "fontWeight": (font.get("variationSettings") or {}).get("wght") or {
            "Regular": 400, "Italic": 400, "Bold": 700, "Extra Bold": 800, "Black": 900,
            "Semi Bold": 600, "Black Italic": 900,
        }.get(font.get("style")),
        "color": None, "bg": None, "radius": None,
    }


def run(directory, *, json_only=False):
    directory = Path(directory).resolve()
    source = json.loads((directory / "source-nodes.json").read_text(encoding="utf-8"))
    reference, actual = source["frames"]
    def icon_context(node, frame):
        path = node["path"]
        while "/" in path:
            path = path.rsplit("/", 1)[0]
            controls = [item["name"] for item in frame["nodes"]
                        if item["path"].startswith(path + "/")
                        and item["name"].startswith(("Text Input - ", "Button - "))]
            if len(controls) == 1:
                return controls[0]
            texts = [item.get("text") for item in frame["nodes"]
                     if item["path"].startswith(path + "/") and item["type"] == "TEXT"]
            if len(texts) == 1:
                return texts[0]
        return None

    eligible = lambda n: n["visible"] and n.get("box") and (n["type"] == "TEXT" or n["name"].startswith("Button - ") or n["name"] == "Icon")
    left = [node for node in reference["nodes"] if eligible(node)]
    right = [node for node in actual["nodes"] if eligible(node)]
    for frame, nodes in ((reference, left), (actual, right)):
        for node in nodes:
            if node["name"] == "Icon":
                context = icon_context(node, frame)
                node["match_name"] = f"Icon for {context}" if context else None
    left = [node for node in left if node["name"] != "Icon" or node["match_name"]]
    right = [node for node in right if node["name"] != "Icon" or node["match_name"]]
    identity = lambda node: (node["type"], node.get("match_name") or node.get("text", node["name"]))
    left_counts, right_counts = Counter(map(identity, left)), Counter(map(identity, right))
    design, comparison, mapping = {}, {}, []
    for node in left:
        key = identity(node)
        if left_counts[key] != 1 or right_counts[key] > 1:
            continue
        matches = [candidate for candidate in right if identity(candidate) == key]
        label = node.get("match_name") or node["name"]
        design[label] = tokens(node, reference)
        comparison[label] = tokens(matches[0], actual) if matches else None
        mapping.append({"label": label, "reference_id": node["id"],
                        "comparison_id": matches[0]["id"] if matches else None})
    page = reference["nodes"][0]["name"] + " — Figma frame comparison"
    findings = compare(page, reference["width"], list(design), design, comparison)
    for finding in findings:
        if finding["category"] == "Missing":
            finding["actual"] = "Not found in comparison frame"
    raw_findings = [dict(finding) for finding in findings]
    findings = group_frame_findings(findings, mapping, reference, actual)
    visual = visual_diff(directory / "images/design.png", directory / "images/comparison.png", directory / "images/diff.png")
    if not visual["pass"]:
        visual_finding = {"page": page, "breakpoint": reference["width"],
                         "label": "Whole frame", "category": "Visual", "property": "Pixel similarity (SSIM)",
                         "expected": ">= 0.97", "actual": str(visual["ssim"]), "severity": "Medium", "related": ""}
        findings.append(visual_finding)
        raw_findings.append(dict(visual_finding))
    result = {"page": page, "breakpoint": reference["width"],
              "status": "FAIL" if any(f["severity"] in {"High", "Medium"} for f in findings) else "PASS",
              "url": f"https://www.figma.com/design/{source['fileKey']}",
              "threshold": .97, "findings": findings,
              "raw_findings": raw_findings,
              "images": {"design": "images/design.png", "live": "images/comparison.png", "diff": "images/diff.png"},
              "coverage": [f"Reference frame {reference['id']}; comparison frame {actual['id']}.",
                           f"{len(mapping)} uniquely identified text, button or contextual icon layers checked. Repeated and generic layers are unverified.",
                           "Typography dimensions and consistent downstream flow shifts are grouped as related measurements. Independent shifts remain separate.",
                           "Both sources are Figma frames. Website DOM, CSS, colour, border and spacing checks are unverified."],
              **{key: value for key, value in visual.items() if key != "pass"}}
    provenance = {"Source": result["url"], "Mode": "Figma frame versus Figma frame",
                  "Reference frame": reference["id"], "Comparison frame": actual["id"]}
    if not json_only:
        build_html([result], directory, directory / "report.html", directory.name, provenance=provenance)
        build_xlsx([result], directory / "findings.xlsx", provenance=provenance)
    (directory / "result.json").write_text(json.dumps({"check": result, "mapping": mapping}, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "ssim": result["ssim"], "findings": len(findings),
                      "excel": str(directory / "findings.xlsx")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    run(args.directory, json_only=args.json_only)
