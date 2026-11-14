"""Prepare an isolated Excel workbook for a Studio run."""
import argparse
import json
import os
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.sources import discover, fetch_frames, figma_url, guard_page, inspect_dom, live_url, suggestions, walk
from backend.worker import write_config
from capture import capture
from common import BusinessError, SystemFault
from demo.make_demo import MAPPING
from figma_client import download_image, extract_tokens
from scripts import run_qa


def configured_token():
    token = os.getenv("FIGMA_TOKEN", "").strip()
    if not token and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment:
                token = str(winreg.QueryValueEx(environment, "FIGMA_TOKEN")[0]).strip()
        except OSError:
            pass
    return token


def choose_frame(frames):
    """Ask the attended Studio user which frame is the comparison reference."""
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("DesignQA — choose the reference design")
    window.attributes("-topmost", True)
    window.geometry("720x420")
    selected = []
    ttk.Label(window, text="This Figma link contains several designs. Choose the one matching your website.",
              wraplength=680).pack(padx=16, pady=14, anchor="w")
    container = ttk.Frame(window)
    container.pack(fill="both", expand=True, padx=16)
    scrollbar = ttk.Scrollbar(container)
    scrollbar.pack(side="right", fill="y")
    listing = tk.Listbox(container, exportselection=False, yscrollcommand=scrollbar.set)
    listing.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listing.yview)
    for frame in frames:
        listing.insert("end", f"{frame['name']} — {frame['width']} × {frame['height']} px — {frame['id']}")
    status = ttk.Label(window, text="Select a frame, then click Compare.")
    status.pack(padx=16, pady=8, anchor="w")

    def confirm():
        selection = listing.curselection()
        if not selection:
            status.config(text="Please select a frame from the list.")
            return
        selected.append(frames[selection[0]])
        window.destroy()

    actions = ttk.Frame(window)
    actions.pack(fill="x", padx=16, pady=(0, 16))
    ttk.Button(actions, text="Cancel", command=window.destroy).pack(side="right")
    ttk.Button(actions, text="Compare", command=confirm).pack(side="right", padx=8)
    listing.bind("<Double-Button-1>", lambda event: confirm())
    try:
        window.mainloop()
    finally:
        try:
            window.destroy()
        except tk.TclError:
            pass
    if not selected:
        raise BusinessError("Frame selection was cancelled.")
    return selected[0]


def prepare(args):
    directory = Path(args.workbook).parent
    directory.mkdir(parents=True, exist_ok=True)
    widths = [] if args.widths == "auto" else [int(width) for width in args.widths.split(",")]
    pages, mappings, coverage = [], [], {}
    if args.mode == "demo":
        variants = [("Baseline", "good"), ("Seeded defects", "buggy")]
        selectors = [{"label": label, "css": css} for label, _, css in MAPPING]
        for width in widths:
            image, styles = directory / f"{width}.png", directory / f"{width}.json"
            baseline = ROOT / "demo/site/good/index.html"
            tokens = capture(baseline.as_uri(), width, image, selectors)
            styles.write_text(json.dumps(tokens), encoding="utf-8")
            for name, variant in variants:
                pages.append(["Y", name, width, str(ROOT / "demo/site" / variant / "index.html"),
                              0.97, str(image), str(styles)])
                mappings.extend([name, width, label, node, css] for label, node, css in MAPPING)
    else:
        key, preferred = figma_url(args.figma)
        live_url(args.live, resolve=True)
        token = configured_token()
        if not token:
            raise BusinessError("One-time setup required: configure FIGMA_TOKEN as a Windows user environment variable. The Figma connection in chat does not provide credentials to UiPath.")
        if token in args.figma or token in args.live:
            raise BusinessError("Remove the Figma token from the input URLs.")
        frames = discover(key, preferred, token)
        if args.widths == "auto":
            chosen = next((frame for frame in frames if frame["id"] == preferred), None)
            if chosen is None:
                defaults_path = ROOT / "config/figma_frames.json"
                defaults = json.loads(defaults_path.read_text(encoding="utf-8")) if defaults_path.exists() else {}
                saved_id = defaults.get(key, {}).get("reference_frame")
                # A frame-specific URL always wins. Defaults apply to a page URL.
                if preferred in {None, "0:1"}:
                    chosen = next((frame for frame in frames if frame["id"] == saved_id), None)
            if chosen is None and len(frames) == 1:
                chosen = frames[0]
            if chosen is None and getattr(args, "interactive_frames", False):
                eligible = [frame for frame in frames if 320 <= frame["width"] <= 2560
                            and 0 < frame.get("height", 0) <= 30000]
                if not eligible:
                    raise BusinessError("No frames within the supported screenshot dimensions were found.")
                chosen = choose_frame(eligible)
            if chosen is None:
                raise BusinessError("Select the reference frame inside Figma, choose Copy link to selection, and use that link. The supplied page link contains multiple possible frames.")
            if not 320 <= chosen["width"] <= 2560:
                raise BusinessError("The selected frame width must be between 320 and 2560 px.")
            preferred = chosen["id"]
            widths = [chosen["width"]]
        selected = {}
        for width in widths:
            supplied = args.desktop_frame if width == 1440 else args.mobile_frame
            explicit = supplied.strip().replace("-", ":")
            candidates = [f for f in frames if f["width"] == width]
            selection = next((f for f in candidates if f["id"] == (explicit or preferred)), None)
            if not selection and not explicit and len(candidates) == 1:
                selection = candidates[0]
            if not selection:
                options = ", ".join(f"{f['name']} ({f['id']})" for f in candidates[:8]) or "none"
                raise BusinessError(f"Choose a {width} px frame ID. Available exact-width frames: {options}.")
            selected[width] = selection["id"]
        docs, urls = fetch_frames(key, list(selected.values()), token)
        for width, frame_id in selected.items():
            image, styles = directory / f"{width}.png", directory / f"{width}.json"
            frame = docs[frame_id]
            download_image(urls[frame_id], image)
            layers = {node["id"]: node for node in walk(frame)}
            tokens = {}
            candidates = suggestions(frame, inspect_dom(args.live, width), width, {})
            for row in candidates:
                if row["confidence"] != "High":
                    continue
                node = row["node_id"]
                label = f"{row['label']} [{node}]"
                tokens[label] = extract_tokens(layers[node], frame["absoluteBoundingBox"])
                mappings.append(["Live website", width, label, node, row["selector"], layers[node]["type"] == "TEXT"])
            coverage[width] = {"frame": frame_id, "mapped": len(tokens), "candidates": len(candidates)}
            styles.write_text(json.dumps(tokens), encoding="utf-8")
            height = int(round(frame["absoluteBoundingBox"]["height"]))
            pages.append(["Y", "Live website", width, args.live, 0.97, str(image), str(styles), height])
    write_config(Path(args.workbook), pages, mappings, [], retries=0)
    (directory / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(pages), "mappings": len(mappings), "coverage": coverage}))


def run_row(args):
    settings, pages, mappings = run_qa.load_config(Path(args.workbook))
    row = next((page for page in pages if page["_row"] == args.row), None)
    if row is None:
        raise BusinessError("The Excel row is disabled or missing.")
    live = str(row["LiveURL"]).startswith(("https://", "http://"))
    if live:
        live_url(row["LiveURL"], resolve=True)
    capture_page = partial(capture, page_setup=guard_page) if live else capture
    result = run_qa.process_row(row, settings, mappings, Path(args.out) / args.run_id, capture_page=capture_page)
    print(json.dumps({key: result.get(key) for key in ("status", "error_type")}))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[result["status"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("demo", "figma"))
    parser.add_argument("--widths")
    parser.add_argument("--row", type=int)
    parser.add_argument("--out")
    parser.add_argument("--run-id")
    parser.add_argument("--interactive-frames", action="store_true")
    for option in ("workbook", "figma", "live", "desktop-frame", "mobile-frame"):
        parser.add_argument("--" + option, default="")
    args = parser.parse_args()
    try:
        if args.row is not None:
            return run_row(args)
        prepare(args)
    except (BusinessError, SystemFault) as err:
        print(json.dumps({"error": str(err), "error_type": type(err).__name__}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

