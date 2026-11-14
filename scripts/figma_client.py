"""Figma REST API client: frame PNG + design tokens for mapped nodes.

Written against the public Figma REST API (GET /v1/images, GET /v1/files/:key/nodes).
Token comes from the FIGMA_TOKEN environment variable - never from a file or log.
Node ids may be written 12:34 or 12-34 (as copied from a Figma URL).
"""
import os
import time

import requests

from common import BusinessError, SystemFault, float_to_hex, log

API = "https://api.figma.com/v1"


def _nid(n):
    return str(n).strip().replace("-", ":")


def _get(url, token, params=None, retries=4):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"X-Figma-Token": token}, params=params, timeout=30, allow_redirects=False)
        except requests.RequestException as e:
            raise SystemFault(f"Figma request failed: {e}")
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "")
            wait = min(30, int(retry_after)) if retry_after.isdecimal() else 5 * (attempt + 1)
            log(f"Figma rate limit, waiting {wait}s")
            time.sleep(wait)
            continue
        if r.status_code in (401, 403):
            raise BusinessError("Figma token invalid or no access to this file")
        if r.status_code == 404:
            raise BusinessError("Figma file or node not found")
        if r.status_code >= 500:
            raise SystemFault(f"Figma server error {r.status_code}")
        if not r.ok or r.is_redirect:
            raise BusinessError(f"Figma API returned HTTP {r.status_code}")
        return r
    raise SystemFault("Figma rate limit persisted after retries")


def _first_text(n):
    if n.get("type") == "TEXT":
        return n
    for c in n.get("children", []) or []:
        t = _first_text(c)
        if t:
            return t
    return None


def _solid(fills):
    for f in fills or []:
        if f.get("type") == "SOLID" and f.get("visible", True):
            return float_to_hex(f["color"])
    return None


def extract_tokens(node, frame_box):
    """One Figma node -> the normalised token dict used by compare_styles."""
    txt = _first_text(node)
    tok = {"fontFamily": None, "fontSize": None, "fontWeight": None, "color": None,
           "bg": None, "radius": None if node.get("type") == "TEXT" else node.get("cornerRadius", 0) or 0}
    if txt:
        st = txt.get("style", {})
        tok.update(fontFamily=st.get("fontFamily"), fontSize=st.get("fontSize"),
                   fontWeight=st.get("fontWeight"), color=_solid(txt.get("fills")))
    if node.get("type") != "TEXT":
        tok["bg"] = _solid(node.get("fills"))
    box = node.get("absoluteBoundingBox")
    if box and frame_box:
        tok.update(x=round(box["x"] - frame_box["x"], 1), y=round(box["y"] - frame_box["y"], 1),
                   w=round(box["width"], 1), h=round(box["height"], 1))
    return tok


def fetch_design(file_key, frame_id, mapping, out_png, scale=1):
    """mapping = [{'label':..., 'node':...}] -> returns {label: tokens}; saves frame PNG."""
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        raise BusinessError("FIGMA_TOKEN environment variable is not set")
    frame_id = _nid(frame_id)
    ids = [frame_id] + [_nid(m["node"]) for m in mapping if m.get("node")]

    img = _get(f"{API}/images/{file_key}", token, {"ids": frame_id, "format": "png", "scale": scale}).json()
    url = (img.get("images") or {}).get(frame_id)
    if not url:
        raise BusinessError(f"Figma could not render frame {frame_id}")
    download_image(url, out_png)


    nodes = _get(f"{API}/files/{file_key}/nodes", token, {"ids": ",".join(ids)}).json().get("nodes", {})
    if frame_id not in nodes or not nodes[frame_id]:
        raise BusinessError(f"Frame {frame_id} not found in file")
    frame_box = nodes[frame_id]["document"].get("absoluteBoundingBox")
    tokens = {}
    for m in mapping:
        n = nodes.get(_nid(m["node"])) if m.get("node") else None
        if n:
            tokens[m["label"]] = extract_tokens(n["document"], frame_box)
    return tokens

def download_image(url, out_png):
    """Download a Figma export without sending the API credential."""
    from urllib.parse import urlsplit

    target = urlsplit(url)
    host = target.hostname or ""
    if target.scheme != "https" or target.username or target.password or not (
        host == "figma.com" or host.endswith(".figma.com") or host.endswith(".amazonaws.com")
    ):
        raise BusinessError("Figma returned an unsupported export host")
    try:
        with requests.get(url, stream=True, timeout=30, allow_redirects=False) as response:
            if response.status_code != 200:
                raise SystemFault(f"Figma export returned HTTP {response.status_code}")
            total = 0
            with open(out_png, "wb") as file:
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > 32 * 1024 * 1024:
                        raise BusinessError("Figma export exceeds the image size limit")
                    file.write(chunk)
    except requests.RequestException:
        raise SystemFault("Figma image download failed") from None

