"""Live page and Figma inputs for the local DesignQA workspace."""
import ipaddress
import re
import socket
from urllib.parse import parse_qs, urlsplit

from scripts import run_qa  # Initializes the legacy engine module path.
from capture import JS_SCROLL
from common import BusinessError, SystemFault
from figma_client import API, _get, _nid


def figma_url(value):
    try:
        url = urlsplit(value)
        path = url.path.strip("/").split("/")
        node = parse_qs(url.query).get("node-id", [""])[0]
        if (url.scheme != "https" or url.netloc.lower() not in {"figma.com", "www.figma.com"}
                or len(path) < 2 or path[0] not in {"design", "file"}
                or not re.fullmatch(r"[A-Za-z0-9]{1,100}", path[1])
                or (node and not re.fullmatch(r"\d+[:-]\d+", node))):
            raise ValueError
        return path[1], _nid(node) if node else None
    except ValueError:
        raise BusinessError("Enter a valid Figma design URL.") from None


def live_url(value, *, resolve=False):
    try:
        url = urlsplit(value)
        host = url.hostname
        if (url.scheme not in {"http", "https"} or not host or "." not in host
                or url.username or url.password or url.port not in {None, 80, 443}
                or any(char.isspace() for char in value) or "\\" in value):
            raise ValueError
        if re.fullmatch(r"[0-9.]+", host):
            if not ipaddress.ip_address(host).is_global:
                raise ValueError
        if host.rstrip(".").endswith((".localhost", ".local", ".internal")):
            raise ValueError
        if resolve:
            addresses = socket.getaddrinfo(host, url.port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(addr[4][0]).is_global for addr in addresses):
                raise ValueError
    except socket.gaierror:
        raise SystemFault("Could not resolve the live website hostname.") from None
    except (ValueError, UnicodeError):
        raise BusinessError("Use a public HTTP or HTTPS website URL.") from None
    return value


def guard_page(page):
    """Filter browser requests in the single-user worker."""
    permitted = {}

    def route_request(route):
        value = route.request.url
        try:
            host = urlsplit(value).hostname
            if host not in permitted:
                permitted[host] = False
                live_url(value, resolve=True)
                permitted[host] = True
            live_url(value)
            if permitted[host]:
                route.continue_()
                return
        except (BusinessError, SystemFault, ValueError):
            pass
        route.abort("blockedbyclient")

    page.route("**/*", route_request)
    page.route_web_socket("**/*", lambda ws: ws.close())


def walk(node):
    stack = [node]
    while stack:
        item = stack.pop()
        if item.get("visible", True):
            yield item
            stack.extend(reversed(item.get("children", [])))


FRAME_TYPES = {"FRAME", "COMPONENT", "INSTANCE", "SECTION"}


def discover(key, preferred, token):
    root = _get(f"{API}/files/{key}", token, {"depth": 4}).json()["document"]
    nodes = {node["id"]: node for node in walk(root)}
    if preferred and preferred not in nodes:
        data = _get(f"{API}/files/{key}/nodes", token, {"ids": preferred, "depth": 1}).json()
        if entry := data.get("nodes", {}).get(preferred):
            nodes[preferred] = entry["document"]
    frames = []
    for node in nodes.values():
        bounds = node.get("absoluteBoundingBox") or {}
        if node["type"] in FRAME_TYPES and bounds.get("width", 0) >= 250 and bounds.get("height", 0) > 0:
            frames.append({"id": node["id"], "name": node["name"],
                           "width": round(bounds["width"]), "height": round(bounds["height"])})
    if not frames:
        raise BusinessError("No suitable frames were found in the Figma file.")
    frames.sort(key=lambda frame: (frame["id"] != preferred, min(abs(frame["width"] - w) for w in (375, 1440))))
    return frames[:200]


def fetch_frames(key, ids, token):
    joined = ",".join(dict.fromkeys(ids))
    data = _get(f"{API}/files/{key}/nodes", token, {"ids": joined}).json().get("nodes", {})
    if any(not data.get(frame_id) for frame_id in ids):
        raise BusinessError("A selected Figma frame is no longer available.")
    urls = _get(f"{API}/images/{key}", token, {"ids": joined, "format": "png", "scale": 1,
                                            "use_absolute_bounds": "true"}).json().get("images", {})
    if any(not urls.get(frame_id) for frame_id in ids):
        raise BusinessError("Figma could not render a selected frame.")
    return {frame_id: data[frame_id]["document"] for frame_id in ids}, urls


DOM = r"""() => {
  function selector(el) {
    if (el.id) {
      const id = '#' + CSS.escape(el.id);
      if (document.querySelectorAll(id).length === 1) return id;
    }
    const parts = [];
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      const tag = CSS.escape(node.localName);
      const pos = Array.from(node.parentElement.children).filter(n => n.localName === node.localName).indexOf(node) + 1;
      parts.unshift(tag + ':nth-of-type(' + pos + ')');
    }
    return 'body > ' + parts.join(' > ');
  }
  const query = 'h1,h2,h3,h4,p,a,button,label,img,input,nav,header,footer,main,section,article,[role],[aria-label],div,span';
  return Array.from(document.querySelectorAll(query)).slice(0, 3500)
    .filter(el => el.getClientRects().length && getComputedStyle(el).visibility === 'visible')
    .slice(0, 800).map(el => ({
      selector: selector(el), tag: el.localName, identity: [el.id, el.getAttribute('class')].filter(Boolean).join(' ').slice(0, 200),
      role: el.getAttribute('role') || '', label: (el.getAttribute('aria-label') || el.getAttribute('alt') ||
        (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ')).slice(0, 200),
      text: (el.innerText || el.textContent || '').trim().slice(0, 200)
    }));
}"""


def inspect_dom(url, width, selectors=()):
    from playwright.sync_api import Error, sync_playwright

    live_url(url, resolve=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, service_workers="block")
                guard_page(page)
                page.set_default_timeout(15000)
                response = page.goto(url, wait_until="domcontentloaded")
                live_url(page.url, resolve=True)
                if response and response.status >= 400:
                    raise BusinessError(f"Website returned HTTP {response.status}.")
                page.evaluate(JS_SCROLL)
                if selectors:
                    return page.evaluate(
                        """selectors => selectors.map(selector => {
                            try { return document.querySelectorAll(selector).length; } catch { return -1; }
                        })""", selectors)
                return page.evaluate(DOM)
            finally:
                browser.close()
    except Error as exc:
        if any(code in str(exc) for code in ("ERR_CONNECTION_REFUSED", "ERR_NAME_NOT_RESOLVED", "ERR_BLOCKED_BY_CLIENT")):
            raise BusinessError("The live website could not be reached.") from None
        raise SystemFault("The browser could not load the live website.") from None


def normal(value):
    return " ".join(re.findall(r"\w+", value.casefold().replace("_", " ").replace("-", " ")))


def suggestions(frame, dom, width, saved):
    rows = []
    for node in walk(frame):
        if node is frame or node.get("type") not in FRAME_TYPES | {"TEXT", "GROUP", "RECTANGLE"}:
            continue
        label = node.get("name") or node["id"]
        name, text = normal(label), normal(node.get("characters", ""))
        eligible = []
        for element in dom:
            signals = []
            score = 0
            if text and text == normal(element["text"]):
                score += 6
                signals.append("Exact text")
                if element["tag"] in {"h1", "h2", "h3", "h4", "a", "button", "p", "label"}:
                    score += 1
            if name and name == normal(element["label"]):
                score += 5
                signals.append("Accessible label")
            if name and name in [normal(part) for part in element["identity"].split()]:
                score += 4
                signals.append("DOM name")
            semantic = element["role"] or {"a": "link", "h1": "heading", "h2": "heading",
                                           "h3": "heading"}.get(element["tag"], element["tag"])
            if semantic in name.split():
                score += 2
                signals.append("Semantic role")
            if score >= 4:
                eligible.append((score, element["selector"], signals))
        eligible.sort(reverse=True)
        selector, confidence, signals = "", "Unmapped", []
        if eligible and (len(eligible) == 1 or eligible[0][0] > eligible[1][0]):
            score, selector, signals = eligible[0]
            confidence = "High" if score >= 6 else "Medium"
        elif eligible:
            confidence, signals = "Ambiguous", ["Multiple equally ranked elements"]
        if node["id"] in saved:
            selector = saved[node["id"]]
            confidence, signals = "Previously approved", ["Saved selector"]
        rows.append({"node_id": node["id"], "label": label, "breakpoint": width,
                     "selector": selector, "confidence": confidence, "signals": signals})
        if len(rows) == 120:
            break
    return rows

