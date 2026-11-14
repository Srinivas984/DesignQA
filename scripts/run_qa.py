"""Design-vs-Live QA Bot - orchestrator CLI.

  python scripts/run_qa.py --list                       # JSON list of enabled rows (for UiPath loop)
  python scripts/run_qa.py --row 3 --run-id R1          # process ONE Pages row (UiPath transaction)
  python scripts/run_qa.py --report --run-id R1         # merge row results -> report.html / findings.xlsx
  python scripts/run_qa.py --all                        # everything in one go (stand-alone use)

Logs go to stderr; the final result is ONE JSON object on stdout.
Exit codes: 0 = all pass, 1 = design differences found, 2 = at least one row could not be processed.
"""
import argparse
import datetime as dt
import json
import shutil
import sys
import time
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BusinessError, SystemFault, ROOT, log, resolve_path, to_url  # noqa: E402
from capture import capture            # noqa: E402
from diff import visual_diff           # noqa: E402
from compare_styles import compare     # noqa: E402
import report as rpt                   # noqa: E402

DEFAULT_SETTINGS = {"ColorTolerance": 8, "FontSizeTolerancePx": 1, "RadiusTolerancePx": 2,
                    "LayoutTolerancePx": 4, "MinRegionArea": 400, "HideSelectors": "",
                    "TimeoutMs": 30000, "MaxRetries": 2}


# ---------- config ----------
def _sheet_rows(ws):
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for i, r in enumerate(rows[1:], start=2):
        if all(v is None for v in r):
            continue
        d = dict(zip(head, r))
        d["_row"] = i
        out.append(d)
    return out


def load_config(path):
    wb = load_workbook(path, data_only=True)
    settings = dict(DEFAULT_SETTINGS)
    for r in _sheet_rows(wb["Settings"]):
        if r.get("Key") and r.get("Value") is not None:
            settings[str(r["Key"]).strip()] = r["Value"]
    pages = [r for r in _sheet_rows(wb["Pages"]) if str(r.get("Enabled", "Y")).strip().upper() in ("Y", "YES", "TRUE", "1")]
    mapping = _sheet_rows(wb["Mapping"])
    return settings, pages, mapping


# ---------- one row ----------
def _safe(s):
    return "".join(ch if ch.isalnum() else "_" for ch in str(s))


def _process_once(row, settings, mapping, run_dir, notify, capture_page):
    page, bp = str(row["PageName"]), int(row["Breakpoint"])
    threshold = float(row.get("Threshold") or 0.97)
    maprows = [m for m in mapping if str(m["PageName"]) == page and int(m["Breakpoint"]) == bp]
    if not maprows and not settings.get("AllowVisualOnly"):
        raise BusinessError(f"No Mapping rows for {page} @ {bp}")
    labels = [m["Label"] for m in maprows]
    base = f"{_safe(page)}_{bp}"
    img_dir = run_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    design_png, live_png, diff_png = img_dir / f"{base}_design.png", img_dir / f"{base}_live.png", img_dir / f"{base}_diff.png"

    # 1) design source: local files (demo / offline) or Figma API
    if row.get("DesignImage") and row.get("DesignStyles"):
        src_img, src_json = resolve_path(row["DesignImage"]), resolve_path(row["DesignStyles"])
        if not src_img.exists() or not src_json.exists():
            raise BusinessError(f"Local design files not found: {src_img} / {src_json}")
        shutil.copy(src_img, design_png)
        design = json.loads(src_json.read_text())
    elif row.get("FigmaFileKey") and row.get("FigmaNodeId"):
        from figma_client import fetch_design
        design = fetch_design(str(row["FigmaFileKey"]), row["FigmaNodeId"],
                              [{"label": m["Label"], "node": m.get("FigmaNodeId")} for m in maprows], design_png)
    else:
        raise BusinessError("Row needs DesignImage+DesignStyles (local) or FigmaFileKey+FigmaNodeId")

    # 2) live page
    hide = [h.strip() for h in str(settings.get("HideSelectors") or "").split(",") if h.strip()]
    notify("capture")
    live = capture_page(to_url(row["LiveURL"]), bp, live_png,
                   [{"label": m["Label"], "css": m["CssSelector"], "text_only": bool(m.get("TextOnly"))} for m in maprows],
                   hide, int(settings["TimeoutMs"]), viewport_height=int(row.get("ViewportHeight") or 900))

    # 3) visual diff + 4) style/layout diff
    notify("visual")
    vd = visual_diff(design_png, live_png, diff_png, threshold, float(settings["MinRegionArea"]))
    tol = {"color": float(settings["ColorTolerance"]), "font_size": float(settings["FontSizeTolerancePx"]),
           "radius": float(settings["RadiusTolerancePx"]), "layout": float(settings["LayoutTolerancePx"])}
    notify("styles")
    findings = compare(page, bp, labels, design, live, tol)

    if not vd["pass"]:
        sev = "High" if vd["ssim"] < threshold - 0.10 else "Medium"
        findings.append({"page": page, "breakpoint": bp, "label": "Whole page", "category": "Visual",
                         "property": "Pixel similarity (SSIM)", "expected": f">= {threshold}",
                         "actual": str(vd["ssim"]), "severity": sev})
    for x, y, w, h in vd["regions"][:8]:
        findings.append({"page": page, "breakpoint": bp, "label": f"Region x={x} y={y}", "category": "Visual",
                         "property": "Changed area", "expected": "matches design", "actual": f"{w}x{h}px differs",
                         "severity": "Medium" if w * h > 40000 else "Low"})
    if abs(vd["height_design"] - vd["height_live"]) > 8:
        findings.append({"page": page, "breakpoint": bp, "label": "Whole page", "category": "Layout",
                         "property": "Page height", "expected": f'{vd["height_design"]}px',
                         "actual": f'{vd["height_live"]}px', "severity": "Medium"})

    status = "FAIL" if any(f["severity"] in ("High", "Medium") for f in findings) else "PASS"
    return {"row": row["_row"], "page": page, "breakpoint": bp, "url": str(row["LiveURL"]), "status": status,
            "ssim": vd["ssim"], "threshold": threshold, "regions": vd["regions"],
            "height_design": vd["height_design"], "height_live": vd["height_live"], "findings": findings,
            "images": {"design": f"images/{design_png.name}", "live": f"images/{live_png.name}",
                       "diff": f"images/{diff_png.name}"}}


def process_row(row, settings, mapping, run_dir, *, notify=lambda stage: None, capture_page=capture):
    t0, retries = time.time(), int(settings["MaxRetries"])
    for attempt in range(retries + 1):
        try:
            res = _process_once(row, settings, mapping, run_dir, notify, capture_page)
            break
        except SystemFault as e:
            log(f"  system fault (attempt {attempt + 1}/{retries + 1}): {e}")
            if attempt == retries:
                res = {"row": row["_row"], "page": str(row["PageName"]), "breakpoint": int(row["Breakpoint"]),
                       "status": "ERROR", "error_type": "SystemFault", "error": str(e), "findings": []}
            else:
                time.sleep(2 * (attempt + 1))
        except BusinessError as e:
            res = {"row": row["_row"], "page": str(row["PageName"]), "breakpoint": int(row["Breakpoint"]),
                   "status": "ERROR", "error_type": "BusinessError", "error": str(e), "findings": []}
            break
    res["seconds"] = round(time.time() - t0, 1)
    (run_dir / "rows").mkdir(parents=True, exist_ok=True)
    (run_dir / "rows" / f"{row['_row']}.json").write_text(json.dumps(res, indent=2))
    log(f"  row {row['_row']} {res['page']}@{res['breakpoint']}: {res['status']}"
        + (f" ({res['error']})" if res["status"] == "ERROR" else f" - {len(res['findings'])} findings, SSIM {res['ssim']}"))
    return res


def summarise(results, run_id, run_dir):
    f = [x for r in results for x in r.get("findings", [])]
    return {"run_id": run_id, "output_dir": str(run_dir), "report": str(run_dir / "report.html"),
            "checks": len(results), "pass": sum(r["status"] == "PASS" for r in results),
            "fail": sum(r["status"] == "FAIL" for r in results), "error": sum(r["status"] == "ERROR" for r in results),
            "high": sum(x["severity"] == "High" for x in f), "medium": sum(x["severity"] == "Medium" for x in f),
            "low": sum(x["severity"] == "Low" for x in f)}


def build_reports(run_dir, run_id):
    results = [json.loads(p.read_text()) for p in sorted((run_dir / "rows").glob("*.json"), key=lambda p: int(p.stem))]
    if not results:
        raise BusinessError("No row results found for this run")
    rpt.build_html(results, run_dir, run_dir / "report.html", run_id)
    rpt.build_xlsx(results, run_dir / "findings.xlsx")
    summ = summarise(results, run_id, run_dir)
    (run_dir / "summary.json").write_text(json.dumps(summ, indent=2))
    return summ


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/pages.xlsx")
    ap.add_argument("--out", default="Output")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--row", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--only", help="with --all: only this PageName")
    a = ap.parse_args()

    try:
        settings, pages, mapping = load_config(resolve_path(a.config))
    except Exception as e:  # noqa: BLE001
        log(f"Cannot read config: {e}")
        print(json.dumps({"error": f"Cannot read config: {e}"}))
        sys.exit(2)

    if a.list:
        print(json.dumps([{"row": p["_row"], "page": p["PageName"], "breakpoint": p["Breakpoint"]} for p in pages]))
        return

    run_id = a.run_id or dt.datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = resolve_path(a.out) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if a.report:
        try:
            print(json.dumps(build_reports(run_dir, run_id)))
        except BusinessError as e:
            print(json.dumps({"error": str(e)})); sys.exit(2)
        return

    if a.row:
        sel = [p for p in pages if p["_row"] == a.row]
        if not sel:
            print(json.dumps({"error": f"Row {a.row} not found or disabled"})); sys.exit(2)
        res = process_row(sel[0], settings, mapping, run_dir)
        print(json.dumps({k: res.get(k) for k in ("row", "page", "breakpoint", "status", "ssim", "error", "error_type")}
                         | {"findings": len(res["findings"]), "high": sum(f["severity"] == "High" for f in res["findings"])}))
        sys.exit({"PASS": 0, "FAIL": 1, "ERROR": 2}[res["status"]])

    if a.all:
        results = []
        for p in pages:
            if a.only and str(p["PageName"]) != a.only:
                continue
            results.append(process_row(p, settings, mapping, run_dir))
        summ = build_reports(run_dir, run_id)
        log(f"\nReport: {summ['report']}")
        print(json.dumps(summ))
        sys.exit(2 if summ["error"] else 1 if summ["fail"] else 0)

    ap.print_help()


if __name__ == "__main__":
    main()

