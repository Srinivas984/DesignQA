"""Visual diff of design PNG vs live PNG (SSIM + red overlay + changed regions).

CLI: python diff.py <design.png> <live.png> <out_diff.png> <threshold> [min_area]
Prints one JSON line on stdout.
"""
import json
import sys

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

from common import BusinessError


def visual_diff(design_png, live_png, out_png, threshold=0.97, min_area=400):
    a, b = cv2.imread(str(design_png)), cv2.imread(str(live_png))
    if a is None or b is None:
        raise BusinessError("Could not read design or live image")
    hd, hl = a.shape[0], int(round(b.shape[0] * a.shape[1] / b.shape[1]))
    b = cv2.resize(b, (a.shape[1], hl), interpolation=cv2.INTER_AREA)   # same width as design
    h = min(a.shape[0], b.shape[0])
    a, b = a[:h], b[:h]

    score, full = ssim(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), full=True)
    mask = cv2.threshold(((1 - full) * 255).astype("uint8"), 40, 255, cv2.THRESH_BINARY)[1]
    mask = cv2.dilate(mask, np.ones((15, 15), np.uint8))               # merge neighbouring pixels

    overlay = b.copy()
    overlay[mask > 0] = (0.55 * overlay[mask > 0] + 0.45 * np.array([0, 0, 255])).astype("uint8")
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for c in contours:
        x, y, w, hh = cv2.boundingRect(c)
        if w * hh >= min_area:
            regions.append([int(x), int(y), int(w), int(hh)])
            cv2.rectangle(overlay, (x, y), (x + w, y + hh), (0, 0, 255), 3)
    regions.sort(key=lambda r: r[2] * r[3], reverse=True)
    cv2.imwrite(str(out_png), overlay)
    return {"ssim": round(float(score), 4), "pass": bool(score >= threshold), "regions": regions,
            "height_design": int(hd), "height_live": int(hl)}


if __name__ == "__main__":
    d, l, o, t = sys.argv[1:5]
    m = float(sys.argv[5]) if len(sys.argv) > 5 else 400
    print(json.dumps(visual_diff(d, l, o, float(t), m)))
