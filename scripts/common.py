"""Shared helpers: errors, logging, colour / font / number normalisation."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class BusinessError(Exception):
    """Expected problem with the input (bad URL, node missing). Do NOT retry."""


class SystemFault(Exception):
    """Technical problem (timeout, crash, rate limit). Safe to retry."""


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def resolve_path(p):
    p = Path(str(p))
    return p if p.is_absolute() else ROOT / p


def to_url(u):
    """http(s) URLs pass through; local paths become file:// URLs."""
    u = str(u).strip()
    if u.lower().startswith(("http://", "https://", "file://")):
        return u
    return resolve_path(u).as_uri()


def rgb_to_hex(s):
    """'rgb(1,2,3)' / 'rgba(1,2,3,0.5)' -> '#010203'. Fully transparent -> None."""
    if not s:
        return None
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+%?))?\s*\)", s)
    if not m:
        return s if s.startswith("#") else None
    r, g, b = (int(round(float(m.group(i)))) for i in (1, 2, 3))
    a = m.group(4)
    if a is not None:
        a = float(a.rstrip("%")) / (100 if a.endswith("%") else 1)
        if a == 0:
            return None
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def float_to_hex(c):
    """Figma colour dict {r,g,b} with 0..1 floats -> '#rrggbb'."""
    return "#{:02x}{:02x}{:02x}".format(*(int(round(c[k] * 255)) for k in "rgb"))


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def color_distance(a, b):
    """Largest per-channel difference between two hex colours."""
    return max(abs(x - y) for x, y in zip(hex_to_rgb(a), hex_to_rgb(b)))


def norm_family(s):
    """First family of a CSS font stack, lower-cased, quotes removed."""
    if not s:
        return None
    return s.split(",")[0].strip().strip("'\"").lower()


def norm_weight(w):
    if w is None or w == "":
        return None
    w = str(w).strip().lower()
    return {"normal": 400, "bold": 700}.get(w) or int(float(w))


def px(v):
    """'12px' / '8px 4px' / 12 -> 12.0 (first value). 'normal' / '' -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"\s*(-?[\d.]+)", str(v))
    return float(m.group(1)) if m else None
