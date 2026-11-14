"""HTML + Excel report builder (single-file HTML with embedded images)."""
import base64
import datetime as dt
import html

import cv2
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}
SEV_COLOR = {"High": "#c62828", "Medium": "#ef8f00", "Low": "#558b2f"}


def _b64(path, max_w=640):
    img = cv2.imread(str(path))
    if img is None:
        return ""
    if img.shape[1] > max_w:
        s = max_w / img.shape[1]
        img = cv2.resize(img, (max_w, int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def _sorted(findings):
    return sorted(findings, key=lambda f: (SEV_ORDER[f["severity"]], f["label"], f["property"]))


def build_html(results, run_dir, out_html, run_id, *, provenance=None):
    e = html.escape
    all_f = [f for r in results for f in r.get("findings", [])]
    count = {s: sum(1 for f in all_f if f["severity"] == s) for s in SEV_ORDER}
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_err = sum(1 for r in results if r["status"] == "ERROR")

    parts = [f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Design QA Report {e(run_id)}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--text:#1d2430;--muted:#5d6b7c;--line:#e1e5ea}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12161c;--card:#1b2129;--text:#e8ecf1;--muted:#9aa7b5;--line:#2b3440}}}}
body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}}
.wrap{{max-width:1200px;margin:0 auto;padding:24px 16px 64px}}
h1{{margin:0 0 4px;font-size:26px}} .sub{{color:var(--muted);margin-bottom:20px}}
.stats{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:110px}}
.stat b{{display:block;font-size:26px}} .stat span{{color:var(--muted);font-size:13px}}
.page{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:24px}}
.page h2{{margin:0 0 6px;font-size:19px}}
.chip{{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:12px;font-weight:700;margin-left:8px}}
.meta{{color:var(--muted);font-size:13px;margin-bottom:12px}}
.imgs{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:12px 0}}
.imgs figure{{margin:0}} .imgs figcaption{{font-size:12px;color:var(--muted);margin-bottom:4px;font-weight:700}}
.imgs img{{width:100%;border:1px solid var(--line);border-radius:6px}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-size:12px;text-transform:uppercase}}
.sev{{font-weight:700}} .err{{color:#c62828;font-weight:700}}
@media(max-width:760px){{.imgs{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Design vs Live QA Report</h1>
<div class="sub">Run {e(run_id)} &middot; generated {dt.datetime.now().strftime('%d %b %Y, %H:%M')}</div>
<div class="stats">
<div class="stat"><b>{len(results)}</b><span>page checks</span></div>
<div class="stat"><b style="color:#2e7d32">{n_pass}</b><span>passed</span></div>
<div class="stat"><b style="color:#c62828">{n_fail}</b><span>failed</span></div>
<div class="stat"><b>{n_err}</b><span>errors</span></div>
<div class="stat"><b style="color:{SEV_COLOR['High']}">{count['High']}</b><span>high issues</span></div>
<div class="stat"><b style="color:{SEV_COLOR['Medium']}">{count['Medium']}</b><span>medium issues</span></div>
<div class="stat"><b style="color:{SEV_COLOR['Low']}">{count['Low']}</b><span>low issues</span></div>
</div>"""]

    if provenance:
        parts.append('<section class="page"><h2>Analysis sources</h2>' + "".join(
            f"<p><strong>{e(key)}</strong> {e(value)}</p>" for key, value in provenance.items()) + "</section>")

    for r in results:
        colour = {"PASS": "#2e7d32", "FAIL": "#c62828", "ERROR": "#6d4c41"}[r["status"]]
        parts.append(f'<section class="page"><h2>{e(r["page"])} @ {r["breakpoint"]}px'
                     f'<span class="chip" style="background:{colour}">{r["status"]}</span></h2>')
        for note in r.get("coverage", []):
            parts.append(f'<div class="meta">{e(note)}</div>')
        if r["status"] == "ERROR":
            parts.append(f'<div class="meta">{e(r.get("error_type",""))}</div><div class="err">{e(r.get("error",""))}</div></section>')
            continue
        parts.append(f'<div class="meta">SSIM {r["ssim"]} (threshold {r["threshold"]}) &middot; '
                     f'{len(r["regions"])} changed regions &middot; page height design {r["height_design"]}px / live {r["height_live"]}px'
                     f' &middot; {e(r["url"])}</div><div class="imgs">')
        for key, cap in (("design", "DESIGN"), ("live", "LIVE"), ("diff", "DIFF (red = mismatch)")):
            parts.append(f'<figure><figcaption>{cap}</figcaption><img alt="{cap}" src="{_b64(run_dir / r["images"][key])}"></figure>')
        parts.append("</div>")
        if r["findings"]:
            parts.append('<div class="tw"><table><tr><th>Severity</th><th>Element</th><th>Type</th><th>Property</th><th>Design</th><th>Live</th></tr>')
            for f in _sorted(r["findings"]):
                parts.append(f'<tr><td class="sev" style="color:{SEV_COLOR[f["severity"]]}">{f["severity"]}</td><td>{e(f["label"])}</td>'
                             f'<td>{f["category"]}</td><td>{e(f["property"])}</td><td>{e(f["expected"])}</td><td>{e(f["actual"])}</td></tr>')
            parts.append("</table></div>")
            notes = sorted({f["recommendation"] for f in r["findings"] if f.get("recommendation")})
            if notes:
                parts.append("<h3>Investigation notes</h3><ul>" + "".join(f"<li>{e(note)}</li>" for note in notes) + "</ul>")
        else:
            parts.append("<div>No differences above tolerance.</div>")
        parts.append("</section>")
    parts.append("</div></body></html>")
    out_html.write_text("".join(parts), encoding="utf-8")


def build_xlsx(results, out_xlsx, *, provenance=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Findings"
    head = ["Page", "Breakpoint", "Severity", "Element", "Type", "Property", "Design (expected)", "Live (actual)"]
    ws.append(head)
    for r in results:
        for f in _sorted(r.get("findings", [])):
            ws.append([f["page"], f["breakpoint"], f["severity"], f["label"], f["category"],
                       f["property"], f["expected"], f["actual"]])
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Page", "Breakpoint", "Status", "SSIM", "Threshold", "Changed regions", "High", "Medium", "Low", "Error"])
    for r in results:
        fs = r.get("findings", [])
        ws2.append([r["page"], r["breakpoint"], r["status"], r.get("ssim"), r.get("threshold"),
                    len(r.get("regions", [])), *(sum(1 for f in fs if f["severity"] == s) for s in SEV_ORDER), r.get("error", "")])
    fills = {"High": "F8D7DA", "Medium": "FFE8B3", "Low": "DDEFC9"}
    for sheet in (ws, ws2):
        for c in sheet[1]:
            c.font = Font(name="Arial", bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2B3A4F")
        for row in sheet.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial")
                c.alignment = Alignment(vertical="top", wrap_text=True)
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(40, max(12, max(len(str(c.value or "")) for c in col) + 2))
        sheet.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2):
        row[2].fill = PatternFill("solid", fgColor=fills[row[2].value])
    if provenance:
        info = wb.create_sheet("Analysis")
        info.append(["Field", "Value"])
        for key, value in provenance.items():
            info.append([key, value])
        info.append(["Breakpoint", "Coverage or investigation note"])
        for result in results:
            notes = list(result.get("coverage", []))
            notes.extend(sorted({f["recommendation"] for f in result["findings"] if f.get("recommendation")}))
            for note in notes:
                info.append([result["breakpoint"], note])
        info.column_dimensions["A"].width = 22
        info.column_dimensions["B"].width = 100
        for sheet in wb:
            for row in sheet:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
    wb.save(out_xlsx)

