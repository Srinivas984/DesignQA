"""Capture a live page: full-page screenshot + computed styles of mapped elements.

CLI (UiPath can call this directly):
  python capture.py <url> <width> <out.png> <selectors.json> <out_styles.json> [hide_selectors_comma]
selectors.json = [{"label": "Hero heading", "css": "h1.hero-title"}, ...]
Exit codes: 0 ok, 3 business error (page unreachable), 4 system fault (retry).
"""
import json
import sys

from common import BusinessError, SystemFault, log, rgb_to_hex, px, norm_weight

JS_STYLE = """(input) => {
  const sel = typeof input === 'string' ? input : input.css;
  const el = document.querySelector(sel);
  if (!el) return null;
  const s = getComputedStyle(el);
  let r = el.getBoundingClientRect();
  if (input.text_only && !/^(H[1-6]|P)$/.test(el.tagName)) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ranges = [];
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (!n.textContent.trim() || n.parentElement.closest('svg')) continue;
      const range = document.createRange(); range.selectNodeContents(n); ranges.push(range.getBoundingClientRect());
    }
    if (ranges.length) {
      const x = Math.min(...ranges.map(r => r.x)), y = Math.min(...ranges.map(r => r.y));
      r = {x, y, width: Math.max(...ranges.map(r => r.right)) - x, height: Math.max(...ranges.map(r => r.bottom)) - y};
    }
  }
  const color = value => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d'); context.fillStyle = value; context.fillRect(0,0,1,1);
    const [r,g,b,a] = context.getImageData(0,0,1,1).data;
    return 'rgba(' + [r,g,b,a / 255].join(',') + ')';
  };
  return {fontFamily: s.fontFamily, fontSize: s.fontSize, fontWeight: s.fontWeight,
          color: color(s.color), bg: color(s.backgroundColor), radius: s.borderTopLeftRadius,
          x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height};
}"""

JS_SCROLL = """async () => {
  await new Promise(res => { let y = 0;
    const t = setInterval(() => { window.scrollBy(0, 500); y += 500;
      if (y >= Math.min(document.documentElement.scrollHeight, 30000)) { clearInterval(t); window.scrollTo(0, 0); res(); } }, 50); });
}"""

FREEZE_CSS = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"


def normalise(raw):
    if raw is None:
        return None
    return {
        "fontFamily": raw["fontFamily"],
        "fontSize": px(raw["fontSize"]),
        "fontWeight": norm_weight(raw["fontWeight"]),
        "color": rgb_to_hex(raw["color"]),
        "bg": rgb_to_hex(raw["bg"]),
        "radius": px(raw["radius"]) or 0.0,
        "x": round(raw["x"], 1), "y": round(raw["y"], 1),
        "w": round(raw["w"], 1), "h": round(raw["h"], 1),
    }


def capture(url, width, out_png, selectors, hide=(), timeout_ms=30000, viewport_height=900, *, page_setup=None):
    from playwright.sync_api import sync_playwright, Error as PWError

    styles = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": int(width), "height": viewport_height},
                                        service_workers="block" if page_setup else "allow")
                if page_setup:
                    page_setup(page)
                page.set_default_timeout(timeout_ms)
                try:
                    resp = page.goto(url, wait_until="networkidle")
                except PWError as e:
                    msg = str(e)
                    if any(k in msg for k in ("ERR_NAME_NOT_RESOLVED", "ERR_FILE_NOT_FOUND", "ERR_CONNECTION_REFUSED")):
                        raise BusinessError(f"Page not reachable: {url}")
                    raise SystemFault(f"Navigation failed: {msg.splitlines()[0]}")
                if resp is not None and resp.status >= 400:
                    raise BusinessError(f"Page returned HTTP {resp.status}: {url}")
                page.add_style_tag(content=FREEZE_CSS)
                for sel in hide:                      # mask dynamic content
                    page.add_style_tag(content=f"{sel}{{visibility:hidden!important}}")
                page.evaluate(JS_SCROLL)              # trigger lazy-loaded images
                page.wait_for_load_state("networkidle")
                if page_setup and page.evaluate("document.documentElement.scrollHeight") > 30000:
                    raise BusinessError("The page exceeds the web screenshot height limit")
                page.screenshot(path=str(out_png), full_page=True)
                for s in selectors:
                    styles[s["label"]] = normalise(page.evaluate(JS_STYLE, s))
            finally:
                browser.close()
    except (BusinessError, SystemFault):
        raise
    except PWError as e:
        raise SystemFault(f"Browser error: {str(e).splitlines()[0]}")
    return styles


if __name__ == "__main__":
    url, width, out_png, sel_file, out_json = sys.argv[1:6]
    hide = [h for h in (sys.argv[6].split(",") if len(sys.argv) > 6 else []) if h.strip()]
    try:
        res = capture(url, width, out_png, json.load(open(sel_file)), hide)
        json.dump(res, open(out_json, "w"), indent=2)
        log("captured", out_png)
    except BusinessError as e:
        log("BUSINESS:", e); sys.exit(3)
    except SystemFault as e:
        log("SYSTEM:", e); sys.exit(4)


