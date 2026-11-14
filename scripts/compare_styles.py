"""Style + layout comparison: Figma/design tokens vs live computed styles."""
from common import color_distance, norm_family, norm_weight, px

DEFAULT_TOL = {"color": 8, "font_size": 1.0, "radius": 2.0, "layout": 4.0}


def _finding(page, bp, label, category, prop, expected, actual, severity):
    return {"page": page, "breakpoint": bp, "label": label, "category": category,
            "property": prop, "expected": str(expected), "actual": str(actual), "severity": severity}


def compare(page, bp, labels, design, live, tol=None):
    t = {**DEFAULT_TOL, **(tol or {})}
    out = []
    for label in labels:
        d, l = design.get(label), live.get(label)
        if d is None:
            out.append(_finding(page, bp, label, "Setup", "Design token", "present", "not found in design", "Low"))
            continue
        if l is None:
            out.append(_finding(page, bp, label, "Missing", "Element", "present", "NOT FOUND on live page", "High"))
            continue

        def add(cat, prop, exp, act, sev):
            out.append(_finding(page, bp, label, cat, prop, exp, act, sev))

        if d.get("fontFamily") and norm_family(d["fontFamily"]) != norm_family(l["fontFamily"]):
            add("Style", "Font family", d["fontFamily"], norm_family(l["fontFamily"]), "High")
        if d.get("fontSize") is not None and abs(d["fontSize"] - (l["fontSize"] or 0)) > t["font_size"]:
            add("Style", "Font size", f'{d["fontSize"]:g}px', f'{(l["fontSize"] or 0):g}px', "Medium")
        if d.get("fontWeight") and norm_weight(d["fontWeight"]) != l["fontWeight"]:
            add("Style", "Font weight", norm_weight(d["fontWeight"]), l["fontWeight"], "Medium")
        if d.get("color") and (not l["color"] or color_distance(d["color"], l["color"]) > t["color"]):
            add("Style", "Text colour", d["color"], l["color"], "Medium")
        if d.get("bg") and (not l["bg"] or color_distance(d["bg"], l["bg"]) > t["color"]):
            add("Style", "Background colour", d["bg"], l["bg"] or "transparent", "Medium")
        if d.get("radius") is not None and abs(d["radius"] - l["radius"]) > t["radius"]:
            add("Style", "Corner radius", f'{d["radius"]:g}px', f'{l["radius"]:g}px', "Low")

        for key, name in (("w", "Width"), ("h", "Height"), ("x", "X position"), ("y", "Y position")):
            if d.get(key) is None:
                continue
            delta = abs(d[key] - l[key])
            if delta > t["layout"]:
                cat = "Layout"
                add(cat, name, f"{d[key]:g}px", f"{l[key]:g}px", "Medium" if delta > 12 else "Low")
    return out
