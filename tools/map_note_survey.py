"""Survey, visualise and re-author KOTOR 1 Area Map notes.

Built for the map-note placement work (see AREA-MAP-NOTE-FIX-PLAN.md). Read-only
against the game install; the only thing it writes is PNGs into an output folder
you name.

Everything works in VANILLA map-pixel space (0..440 x 0..256). That space is
resolution independent: the patched game scales the art and the markers by the
same kx/ky, so a correction expressed here is correct at every resolution.

Commands
--------
  survey [outfile.csv]
        Every map note in the game: map pixel, whether the engine draws it at
        all, distance to the nearest gameplay object, and what the map artwork
        looks like underneath. Prints a summary; optionally writes a CSV.

  render <module> [outdir] [zoom]
        Annotated PNG of one module: the real map background with every map
        note (red, labelled) and every gameplay object (cyan) drawn on it.
        This is the review surface - it shows exactly where a note lands.

  renderall [outdir] [zoom]
        render, for every module that has map notes.

  target <module> <note-tag-or-index> <px> <py>
        Authoring helper. Given a target map pixel read off a render, print the
        corrected XPosition/YPosition for that note and the world-space delta.

Typical workflow
----------------
  python tools/map_note_survey.py renderall output/mapnotes
  ...look at the PNGs, pick where each bad note SHOULD be...
  python tools/map_note_survey.py target ebo_m12aa Engine 217 229
"""

from __future__ import annotations

import os
import sys
import math

import map_calibration as mc


# --------------------------------------------------------------------------
def _nearest_object_distance(cal, note_px, objects):
    """Distance in map pixels from a note to the closest gameplay object.
    Gameplay objects are a decent proxy for 'where the playable space is':
    they are placed by the same designers against the same geometry, and they
    demonstrably land on the walkable art (87% of ebo_m12aa's 71 objects do,
    with no shift applied)."""
    best = float("inf")
    for _lst, _tag, wx, wy in objects:
        px, py = cal.to_pixel(wx, wy)
        d = math.hypot(px - note_px[0], py - note_px[1])
        if d < best:
            best = d
    return best


def _art_under(texture, px, py, radius=2):
    """Fraction of a small patch of map art that is unmapped (black), and the
    mean luminance. Returns (black_fraction, luminance) or (None, None)."""
    if texture is None:
        return None, None
    w, h = texture.size
    pix = texture.load()
    n = black = lum = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = px + dx, py + dy
            if 0 <= x < w and 0 <= y < h:
                r, g, b = pix[x, y]
                n += 1
                lum += r + g + b
                if r + g + b <= 40:
                    black += 1
    if not n:
        return None, None
    return black / n, lum / (3.0 * n)


# --------------------------------------------------------------------------
def cmd_survey(argv):
    out_csv = argv[0] if argv else None
    rows = []
    for mod in mc.iter_modules():
        if not mod.notes:
            continue
        cal = mod.calibration
        tex = mc.load_map_texture(mod.area)
        for n in mod.notes:
            px = cal.to_pixel(n.x, n.y)
            blackness, lum = _art_under(tex, px[0], px[1])
            rows.append({
                "module": mod.name, "area": mod.area,
                "north_axis": cal.north_axis,
                "index": n.index, "tag": n.tag, "strref": n.strref,
                "name": mc.strref_text(n.strref),
                "world_x": n.x, "world_y": n.y,
                "px": px[0], "py": px[1],
                "drawn": cal.in_bounds(*px),
                "dist_to_object": _nearest_object_distance(cal, px, mod.objects),
                "black_frac": blackness, "luminance": lum,
            })

    modules = {r["module"] for r in rows}
    drawn = [r for r in rows if r["drawn"]]
    print("map notes: %d across %d modules" % (len(rows), len(modules)))
    print("drawn by the engine: %d    rejected by the 0..440/0..256 bound check: %d"
          % (len(drawn), len(rows) - len(drawn)))

    na = {}
    for r in rows:
        na[r["north_axis"]] = na.get(r["north_axis"], 0) + 1
    print("notes by NorthAxis:", dict(sorted(na.items())),
          "(2 and 3 need the axis swap; omitting it misplaces them)")

    bad = [r for r in rows if not r["drawn"]]
    if bad:
        print("\nNEVER DRAWN (out of bounds):")
        for r in bad:
            print("   %-14s %-18s %-22s px(%d,%d)"
                  % (r["module"], r["tag"], r["name"][:22], r["px"], r["py"]))

    onblack = [r for r in drawn if r["black_frac"] is not None and r["black_frac"] >= 0.6]
    print("\nON UNMAPPED (BLACK) ART - unambiguously misplaced: %d" % len(onblack))
    for r in sorted(onblack, key=lambda r: -r["black_frac"]):
        print("   %-14s %-18s %-22s px(%3d,%3d) black=%.0f%% dist=%.0f"
              % (r["module"], r["tag"], r["name"][:22], r["px"], r["py"],
                 100 * r["black_frac"], r["dist_to_object"]))

    ds = sorted(r["dist_to_object"] for r in drawn)
    if ds:
        def pct(q):
            return ds[int(q * (len(ds) - 1))]
        print("\ndistance from a note to the nearest gameplay object (map px):")
        print("   p50=%.1f  p75=%.1f  p90=%.1f  p95=%.1f  p99=%.1f  max=%.1f"
              % (pct(.5), pct(.75), pct(.9), pct(.95), pct(.99), ds[-1]))
        print("   for scale: the marker icon is a FIXED 14x14 px (20x20 selected),")
        print("   so anything past ~7 px already reads as 'not on the thing'.")

    print("\nworst 30 by distance to nearest gameplay object:")
    for r in sorted(drawn, key=lambda r: -r["dist_to_object"])[:30]:
        print("   %-14s NA=%d %-18s %-22s px(%3d,%3d) dist=%5.1f"
              % (r["module"], r["north_axis"], r["tag"], r["name"][:22],
                 r["px"], r["py"], r["dist_to_object"]))

    if out_csv:
        import csv
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nwrote %s (%d rows)" % (out_csv, len(rows)))


# --------------------------------------------------------------------------
def _font(size):
    from PIL import ImageFont
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_module(mod, outdir, zoom=4):
    from PIL import Image, ImageDraw

    tex = mc.load_map_texture(mod.area)
    cal = mod.calibration
    W, H = int(mc.MAP_W), int(mc.MAP_H)
    if tex is None:
        base = Image.new("RGB", (W, H), (12, 12, 16))
    else:
        base = Image.new("RGB", (W, H), (0, 0, 0))
        base.paste(tex, (0, 0))
    img = base.resize((W * zoom, H * zoom), Image.NEAREST)
    # headroom at the bottom for the legend
    canvas = Image.new("RGB", (img.width, img.height + 26 * zoom // 2), (18, 18, 22))
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    small = _font(max(10, 3 * zoom))
    big = _font(max(12, 4 * zoom))

    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(60, 90, 60))

    for _lst, _tag, wx, wy in mod.objects:
        px, py = cal.to_pixel(wx, wy)
        x, y = (px + 0.5) * zoom, (py + 0.5) * zoom
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(0, 210, 210))

    for n in mod.notes:
        px, py = cal.to_pixel(n.x, n.y)
        x, y = (px + 0.5) * zoom, (py + 0.5) * zoom
        oob = not cal.in_bounds(px, py)
        colour = (255, 200, 0) if oob else (255, 40, 40)
        # the game's own fixed 14x14 icon, to scale
        d.ellipse([x - 7 * zoom / 2, y - 7 * zoom / 2,
                   x + 7 * zoom / 2, y + 7 * zoom / 2], outline=(255, 255, 255))
        r = 4 * zoom / 2
        d.ellipse([x - r, y - r, x + r, y + r], outline=colour, width=max(2, zoom // 2))
        d.line([x - r * 2, y, x + r * 2, y], fill=colour)
        d.line([x, y - r * 2, x, y + r * 2], fill=colour)
        label = "%d %s" % (n.index, mc.strref_text(n.strref) or n.tag)
        if oob:
            label += " [OFF-MAP px %d,%d]" % (px, py)
        d.text((x + r * 2 + 2, y - 6 * zoom / 2), label, fill=(255, 235, 120), font=small)

    d.text((6, img.height + 4),
           "%s  (area %s, NorthAxis %d)   red=map note, white ring=its real 14px icon, cyan=gameplay object"
           % (mod.name, mod.area, cal.north_axis), fill=(220, 220, 220), font=big)
    d.text((6, img.height + 6 + 5 * zoom),
           "map-pixel space 0..440 x 0..256  -  1 px here = %d px at 2560x1600" % zoom,
           fill=(150, 150, 150), font=small)

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "%s.png" % mod.name)
    canvas.save(path)
    return path


def cmd_render(argv):
    if not argv:
        print("usage: render <module> [outdir] [zoom]")
        return 2
    name = argv[0]
    outdir = argv[1] if len(argv) > 1 else os.path.join("output", "mapnotes")
    zoom = int(argv[2]) if len(argv) > 2 else 4
    mod = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules", name + ".rim"))
    if mod is None:
        print("no map data for", name)
        return 1
    print("wrote", render_module(mod, outdir, zoom))


def cmd_renderall(argv):
    outdir = argv[0] if argv else os.path.join("output", "mapnotes")
    zoom = int(argv[1]) if len(argv) > 1 else 4
    n = 0
    for mod in mc.iter_modules():
        if not mod.notes:
            continue
        render_module(mod, outdir, zoom)
        n += 1
    print("rendered %d modules into %s" % (n, outdir))


# --------------------------------------------------------------------------
def cmd_target(argv):
    if len(argv) < 4:
        print("usage: target <module> <note-tag-or-index> <px> <py>")
        return 2
    name, ident, px, py = argv[0], argv[1], float(argv[2]), float(argv[3])
    mod = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules", name + ".rim"))
    if mod is None:
        print("no map data for", name)
        return 1
    cal = mod.calibration
    note = None
    for n in mod.notes:
        if n.tag.lower() == ident.lower() or str(n.index) == ident:
            note = n
            break
    if note is None:
        print("no map note %r in %s. Notes: %s"
              % (ident, name, ", ".join("%d:%s" % (n.index, n.tag) for n in mod.notes)))
        return 1

    cur = cal.to_pixel(note.x, note.y)
    nx, ny = cal.to_world(px, py)
    print("%s  note #%d  %s (%s)" % (mod.name, note.index, note.tag,
                                     mc.strref_text(note.strref)))
    print("  current  map px (%3d,%3d)   world (%.6f, %.6f)" % (cur[0], cur[1], note.x, note.y))
    print("  target   map px (%3g,%3g)   world (%.6f, %.6f)" % (px, py, nx, ny))
    print("  delta    map px (%+.1f,%+.1f)  world (%+.6f, %+.6f)"
          % (px - cur[0], py - cur[1], nx - note.x, ny - note.y))
    print("  round-trip check: new world -> map px %s" % (cal.to_pixel(nx, ny),))
    print()
    print("  GFF edit:  WaypointList[%d].XPosition = %.6f" % (note.index, nx))
    print("             WaypointList[%d].YPosition = %.6f" % (note.index, ny))
    print("  (ZPosition unchanged at %.6f - the map transform ignores Z)" % note.z)


# --------------------------------------------------------------------------
COMMANDS = {
    "survey": cmd_survey,
    "render": cmd_render,
    "renderall": cmd_renderall,
    "target": cmd_target,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
