"""Diagnostic: list every ink component on an annotated atlas page.

Prints, per component, its size, bounding box, centroid and the distance from
its nearest point to the nearest note anchor. Used to work out why the ingest
reader flagged a page, without having to eyeball the PNG.

    python tools/atlas_ink_debug.py <dir> [module ...]
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_note_atlas as mna


def anchors_for(rows):
    a = []
    for r in rows:
        a.append((r, float(r["anchor_img_x"]), float(r["anchor_img_y"]), "crosshair"))
        a.append((r, float(r["badge_img_x"]), float(r["badge_img_y"]), "badge"))
        if r["live_img_x"]:
            a.append((r, float(r["live_img_x"]), float(r["live_img_y"]), "live"))
    return a


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = argv[0]
    only = set(argv[1:])
    index = os.path.join(src, "atlas_index.csv")
    if not os.path.exists(index):
        index = os.path.join(root, "output", "atlas", "atlas_index.csv")
    by_module = {}
    with open(index, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            by_module.setdefault(r["module"], []).append(r)

    from PIL import Image

    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith(".png"):
            continue
        mod = fn[:-4]
        if mod not in by_module or (only and mod not in only):
            continue
        rows = by_module[mod]
        r0 = rows[0]
        x0, y0 = int(r0["panel_x0"]), int(r0["panel_y0"])
        pw, ph = int(r0["panel_w"]), int(r0["panel_h"])
        im = Image.open(os.path.join(src, fn)).convert("RGB")
        comps = [c for c in mna.ink_components(im, (x0, y0, pw, ph)) if len(c) >= 3]
        if not comps:
            continue
        anc = anchors_for(rows)
        print("== %s  (%d components)" % (mod, len(comps)))
        for i, comp in enumerate(sorted(comps, key=lambda c: -len(c))):
            xs = [p[0] for p in comp]
            ys = [p[1] for p in comp]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            best = None
            for (row, ax, ay, kind) in anc:
                for (qx, qy) in comp:
                    d = (qx - ax) ** 2 + (qy - ay) ** 2
                    if best is None or d < best[0]:
                        best = (d, row, kind)
            d = best[0] ** 0.5
            span = max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                       for a in (comp[0],) for b in comp)
            print("   c%-2d n=%-5d bbox=(%d,%d)-(%d,%d) centroid=(%.0f,%.0f) "
                  "span~%.0f  nearest: #%s %s via %s at %.0f px"
                  % (i, len(comp), min(xs), min(ys), max(xs), max(ys), cx, cy,
                     span, best[1]["note_index"], best[1]["name"][:22],
                     best[2], d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
