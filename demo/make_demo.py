"""Builds the demo: a 'good' site (matches the design), a 'buggy' copy with 5 seeded bugs,
a simulated Figma export (design PNG + tokens JSON) and config/pages.xlsx.
Run once:  python demo/make_demo.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from capture import capture  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill, Alignment  # noqa: E402

GOOD = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Brewly</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;color:#2b2118;background:#fffaf3}
nav{height:72px;display:flex;align-items:center;justify-content:space-between;padding:0 64px;background:#2b2118}
.logo{font-family:Georgia,serif;font-size:24px;font-weight:700;color:#fffaf3}
nav a{color:#e8d9c4;font-size:16px;margin-left:24px;text-decoration:none}
.hero{height:420px;padding:72px 64px;position:relative;background:#f3e6d2;overflow:hidden}
.badge{position:absolute;top:32px;right:64px;background:#c8553d;color:#fff;font-size:14px;font-weight:700;padding:8px 16px;border-radius:999px}
.hero h1{font-family:Georgia,serif;font-size:48px;font-weight:700;line-height:56px;max-width:640px;color:#2b2118}
.hero p.sub{font-size:20px;line-height:30px;max-width:560px;margin-top:20px;color:#5a4636;position:relative}
.cta{display:inline-block;margin-top:32px;background:#c8553d;color:#ffffff;font-size:18px;font-weight:700;padding:16px 32px;border-radius:8px;text-decoration:none}
.features{display:flex;gap:24px;padding:64px}
.card{flex:1;background:#ffffff;border-radius:12px;padding:32px;height:220px;border:1px solid #eadfce}
.card h3{font-family:Georgia,serif;font-size:24px;color:#2b2118;margin-bottom:12px}
.card p{font-size:16px;line-height:24px;color:#5a4636}
footer{height:96px;display:flex;align-items:center;justify-content:center;background:#2b2118;color:#e8d9c4;font-size:14px}
@media(max-width:768px){
 nav{padding:0 24px} nav a{display:none}
 .hero{height:500px;padding:56px 24px} .hero h1{font-size:34px;line-height:42px}
 .badge{right:24px;top:16px}
 .features{flex-direction:column;padding:32px 24px} .card{flex:none;height:200px}
}
</style></head><body>
<nav><div class="logo">Brewly</div><div><a href="#">Menu</a><a href="#">Stores</a><a href="#">Contact</a></div></nav>
<section class="hero">
 <div class="badge">New: Cold brew</div>
 <h1>Small-batch coffee, delivered fresh</h1>
 <p class="sub">Roasted on Monday, at your door by Wednesday. Pick a blend, set a schedule, skip any time.</p>
 <a class="cta" href="#">Start my box</a>
</section>
<section class="features">
 <div class="card"><h3>Fresh roast</h3><p>Every bag is roasted to order and sealed within hours.</p></div>
 <div class="card"><h3>Flexible plans</h3><p>Weekly, fortnightly or monthly. Pause or cancel whenever.</p></div>
 <div class="card"><h3>Fair sourcing</h3><p>We pay farmers above fair-trade prices, with full traceability.</p></div>
</section>
<footer>&copy; 2026 Brewly Coffee Co.</footer>
</body></html>
"""

# five seeded bugs: font size, button colour, card radius, missing badge, shifted subtitle
BUGS = [
    ("font-size:48px;font-weight:700;line-height:56px", "font-size:44px;font-weight:700;line-height:56px"),
    ("background:#c8553d;color:#ffffff;font-size:18px", "background:#d98b2b;color:#ffffff;font-size:18px"),
    ("background:#ffffff;border-radius:12px", "background:#ffffff;border-radius:4px"),
    ('<div class="badge">New: Cold brew</div>', ""),
    ("margin-top:20px;color:#5a4636;position:relative}", "margin-top:20px;color:#5a4636;position:relative;top:20px}"),
]

MAPPING = [  # label, figma node id (example ids), css selector
    ("Nav logo", "1:101", ".logo"),
    ("Hero heading", "1:110", ".hero h1"),
    ("Hero subtitle", "1:111", ".hero p.sub"),
    ("Promo badge", "1:112", ".badge"),
    ("CTA button", "1:113", ".cta"),
    ("Feature card 1", "1:120", ".card:nth-child(1)"),
    ("Feature title", "1:121", ".card h3"),
    ("Footer text", "1:130", "footer"),
]
BREAKPOINTS = [1440, 375]


def main():
    (ROOT / "demo/site/good").mkdir(parents=True, exist_ok=True)
    (ROOT / "demo/site/buggy").mkdir(parents=True, exist_ok=True)
    (ROOT / "demo/design").mkdir(parents=True, exist_ok=True)
    (ROOT / "config").mkdir(exist_ok=True)
    buggy = GOOD
    for old, new in BUGS:
        assert old in buggy, old
        buggy = buggy.replace(old, new)
    (ROOT / "demo/site/good/index.html").write_text(GOOD, encoding="utf-8")
    (ROOT / "demo/site/buggy/index.html").write_text(buggy, encoding="utf-8")

    # simulated Figma export: frame PNG + design tokens (what figma_client.py returns for a real file)
    sels = [{"label": l, "css": c} for l, _, c in MAPPING]
    good_url = (ROOT / "demo/site/good/index.html").as_uri()
    for bp in BREAKPOINTS:
        tokens = capture(good_url, bp, ROOT / f"demo/design/home_{bp}.png", sels)
        (ROOT / f"demo/design/home_{bp}.json").write_text(json.dumps(tokens, indent=2))

    make_config()
    print("Demo built.")


def make_config():
    wb = Workbook()
    blue, head_fill = Font(name="Arial", color="0000FF"), PatternFill("solid", fgColor="2B3A4F")

    ws = wb.active
    ws.title = "Pages"
    cols = ["Enabled", "PageName", "Breakpoint", "LiveURL", "Threshold", "FigmaFileKey", "FigmaNodeId", "DesignImage", "DesignStyles"]
    ws.append(cols)
    for name, site in (("Home_Baseline", "good"), ("Home_Buggy", "buggy")):
        for bp in BREAKPOINTS:
            ws.append(["Y", name, bp, f"demo/site/{site}/index.html", 0.97, None, None,
                       f"demo/design/home_{bp}.png", f"demo/design/home_{bp}.json"])
    ws.append(["N", "Example_Figma_Row", 1440, "https://your-site.example.com/", 0.97, "AbC123FileKey", "12:34", None, None])

    wm = wb.create_sheet("Mapping")
    wm.append(["PageName", "Breakpoint", "Label", "FigmaNodeId", "CssSelector"])
    for name in ("Home_Baseline", "Home_Buggy"):
        for bp in BREAKPOINTS:
            for label, node, css in MAPPING:
                wm.append([name, bp, label, node, css])

    wsett = wb.create_sheet("Settings")
    wsett.append(["Key", "Value", "Meaning"])
    for k, v, m in [
        ("ColorTolerance", 8, "Max per-channel RGB difference (0-255) before a colour is flagged"),
        ("FontSizeTolerancePx", 1, "Font size difference allowed, in px"),
        ("RadiusTolerancePx", 2, "Corner radius difference allowed, in px"),
        ("LayoutTolerancePx", 4, "Position / size difference allowed, in px"),
        ("MinRegionArea", 400, "Ignore changed pixel regions smaller than this (px squared) - removes noise"),
        ("HideSelectors", "", "Comma-separated CSS selectors to hide before screenshot (ads, carousels, dates)"),
        ("TimeoutMs", 30000, "Page load timeout"),
        ("MaxRetries", 2, "Retries for technical (system) faults only"),
    ]:
        wsett.append([k, v, m])

    wl = wb.create_sheet("Legend")
    for line in [
        "HOW TO USE THIS WORKBOOK",
        "Edit the cells in BLUE font (Pages, Mapping, Settings sheets). Do not rename sheets or column headers.",
        "Pages: one row = one page at one breakpoint. Set Enabled to Y or N.",
        "  Local/demo mode: fill DesignImage + DesignStyles (paths relative to the project folder).",
        "  Figma mode: fill FigmaFileKey + FigmaNodeId (frame id) and leave DesignImage/DesignStyles empty. Needs the FIGMA_TOKEN environment variable.",
        "  LiveURL can be an https URL or a local html path.",
        "Mapping: links each design element (Label + FigmaNodeId) to its CSS selector on the live page, per PageName + Breakpoint.",
        "Example row: the disabled 'Example_Figma_Row' in Pages shows the expected format for Figma mode.",
    ]:
        wl.append([line])
    wl["A1"].font = Font(name="Arial", bold=True, size=12)

    for sheet in (ws, wm, wsett):
        for c in sheet[1]:
            c.font, c.fill = Font(name="Arial", bold=True, color="FFFFFF"), head_fill
        for row in sheet.iter_rows(min_row=2):
            for c in row:
                c.font = blue
                c.alignment = Alignment(vertical="top")
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in col) + 2))
        sheet.freeze_panes = "A2"
    for row in wsett.iter_rows(min_row=2):
        row[2].font = Font(name="Arial", color="000000")
    for r in wl.iter_rows(min_row=2):
        r[0].font = Font(name="Arial")
    wl.column_dimensions["A"].width = 140
    wb.save(ROOT / "config/pages.xlsx")


if __name__ == "__main__":
    main()
