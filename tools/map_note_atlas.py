"""Build a printable/annotatable atlas of every KOTOR 1 Area Map and its notes.

Purpose (user decision, 2026-08-28): automatic placement has too many variables,
so the remaining map-note positions are being authored **by hand**. This tool
produces the surface for that: one image per module, showing the real map art at
4x with every map note marked and numbered, a legend naming each note, and a
generous empty canvas to draw on.

THE ANNOTATION CONTRACT (this is what makes ingest reliable - do not change one
half without the other)
------------------------------------------------------------------------------
The reviewer marks a correction as a **magenta line from the note's marker to
where that note should be**, ending in a small circle or blob at the destination.

- **Magenta `#FF00FF`** is the ink. Verified across all 88 distinct map textures:
  **zero** magenta pixels occur in the game's own art, while saturated red does
  occur (144 px in `m17ab` alone), so magenta is the only colour that cannot be
  confused with the map. Pure red is accepted as a fallback and detected too, but
  magenta is preferred.
- **Identity comes from the line, not from handwriting.** The end of the drawn
  stroke nearest a known marker identifies the note (every marker's exact image
  coordinate is recorded in `atlas_index.csv`); the far end is the target. No
  digit recognition, no guessing by proximity of a lone circle.
- Nothing else on the image is magenta, and no atlas element even approaches it:
  the art is greyscale-ish, markers are yellow/green, floor wash is teal,
  fiducials are cyan.
- Untouched note = leave it exactly where it is. Absence of ink means "fine".

Every image also carries **four cyan fiducial squares** whose centres are
recorded in the index, so a resized or slightly cropped return can still be
mapped back to map-pixel space exactly.

WHAT IS DRAWN PER NOTE
----------------------
- **Yellow crosshair** at the note's *authored* (vanilla) position - the identity
  anchor, because the exe correction table keys on the vanilla world position.
- **Thin white ring**, radius 7 map px: the game's real 14x14 px icon, to scale,
  so "would this icon actually cover the room it names" is judgeable by eye.
- **Numbered yellow badge**, offset clear of the point so the art underneath and
  the space around it stay free to draw on.
- **Green crosshair + connector** when our live exe table already moves that note:
  green is where the game draws it *today*. The atlas therefore doubles as a
  review of the 175 corrections already applied.

Coordinate chain, for the ingest step
-------------------------------------
    image px -> (subtract panel origin, divide by zoom) -> vanilla map px
             -> cal.to_world(px, py)                    -> world XPosition/YPosition

`map_note_survey.py target <module> <note> <px> <py>` already performs the last
leg and prints the corrected world position, and `note_corrections.py` already
accepts a hand-authored target as an `override` decision with `target_px`. So
ingest writes decision rows; no new patch machinery is needed.

Commands
--------
  build [outdir] [--zoom N] [--nofloor] [--only <module>[,<module>...]]
        Render the atlas plus `atlas_index.csv`. Default outdir output/atlas,
        default zoom 4 (1 map px = 4 image px, so hand precision of +/-3 image px
        is under one map pixel).
"""

from __future__ import annotations

import csv
import os
import sys

import map_calibration as mc

ZOOM = 4
PAD = 28
TITLE_H = 84
FOOTER_H = 122
LEGEND_W = 560
FIDUCIAL = 20          # cyan square side, centres recorded in the index
INSET = 18             # fiducial centre inset from the canvas edge

BG = (16, 16, 20)
PANEL_EDGE = (70, 100, 70)
INK_NOTE = (255, 210, 0)        # authored position
INK_LIVE = (60, 230, 90)        # where our table draws it now
INK_RING = (235, 235, 235)
INK_FLOOR = (0, 150, 150, 40)   # faint walkable wash (RGBA)
INK_FIDUCIAL = (0, 255, 255)
TEXT = (226, 226, 226)
TEXT_DIM = (150, 150, 155)

# Reserved for the reviewer. Nothing in this file may draw in these.
INK_USER = (255, 0, 255)


def _font(size, bold=False):
    from PIL import ImageFont
    names = (("arialbd.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf") if bold
             else ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"))
    for nm in names:
        try:
            return ImageFont.truetype(nm, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_live_corrections(root):
    """{(module, note_index): (px, py)} from the corrections the exe holds."""
    path = os.path.join(root, "output", "note_corrections.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            px, py = r["new_px"].split(",")
            out[(r["module"], int(r["note_index"]))] = (int(px), int(py))
    return out


def _badge_spot(x, y, panel, taken, off=30):
    """A badge position clear of the point, the panel edge and other badges."""
    x0, y0, x1, y1 = panel
    for dx, dy in ((off, -off), (off, off), (-off, -off), (-off, off),
                   (0, -off - 8), (0, off + 8), (off + 18, 0), (-off - 18, 0)):
        bx, by = x + dx, y + dy
        if not (x0 + 16 <= bx <= x1 - 16 and y0 + 16 <= by <= y1 - 16):
            continue
        if all((bx - tx) ** 2 + (by - ty) ** 2 > 34 ** 2 for tx, ty in taken):
            return bx, by
    return x + off, y - off


def render_module(mod, outdir, live, geom=None, zoom=ZOOM):
    from PIL import Image, ImageDraw

    W, H = int(mc.MAP_W), int(mc.MAP_H)
    tex = mc.load_map_texture(mod.area)
    art = Image.new("RGB", (W, H), (10, 10, 12))
    if tex is not None:
        art.paste(tex.convert("RGB").crop((0, 0, W, H)), (0, 0))
    art = art.resize((W * zoom, H * zoom), Image.NEAREST)

    cw = PAD + art.width + PAD + LEGEND_W + PAD
    ch = TITLE_H + art.height + FOOTER_H
    canvas = Image.new("RGB", (cw, ch), BG)
    px0, py0 = PAD, TITLE_H
    canvas.paste(art, (px0, py0))
    panel = (px0, py0, px0 + art.width, py0 + art.height)

    # walkable floor, as a faint wash on its own layer so it never hides art
    if geom is not None:
        wash = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        wd = ImageDraw.Draw(wash)
        cal = mod.calibration
        for room in geom.rooms:
            for tri in room.tris:
                pts = []
                for wx, wy in tri:
                    p = cal.to_pixel(wx, wy, integer=False)
                    pts.append((px0 + p[0] * zoom, py0 + p[1] * zoom))
                wd.polygon(pts, fill=INK_FLOOR)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), wash).convert("RGB")

    d = ImageDraw.Draw(canvas)
    f_title = _font(30, bold=True)
    f_sub = _font(17)
    f_legend = _font(19)
    f_small = _font(15)
    f_badge = _font(17, bold=True)

    d.rectangle([px0 - 1, py0 - 1, panel[2], panel[3]], outline=PANEL_EDGE)

    cal = mod.calibration
    rows = []
    taken = []
    # How close is each note's nearest neighbour, in MAP pixels? Two notes 1 map
    # px apart (manm28aa has two such pairs) cannot be told apart by which
    # crosshair a hand-drawn line starts from, so those are flagged and the
    # numbered badge - always >= 34 px clear of any other badge - becomes the
    # anchor to draw from instead.
    pixels = [cal.to_pixel(n.x, n.y) for n in mod.notes]
    crowd = []
    for i, p in enumerate(pixels):
        others = [((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5
                  for j, q in enumerate(pixels) if j != i]
        crowd.append(min(others) if others else 999.0)

    for num, n in enumerate(mod.notes, 1):
        p = cal.to_pixel(n.x, n.y)
        drawn = cal.in_bounds(*p)
        cx = px0 + (p[0] + 0.5) * zoom
        cy = py0 + (p[1] + 0.5) * zoom
        clamped = False
        if not drawn:                      # keep it visible at the nearest edge
            cx = min(max(cx, px0 + 8), panel[2] - 8)
            cy = min(max(cy, py0 + 8), panel[3] - 8)
            clamped = True

        # the engine's real 14x14 icon, to scale
        r_icon = 7 * zoom / 2.0
        d.ellipse([cx - r_icon, cy - r_icon, cx + r_icon, cy + r_icon],
                  outline=INK_RING)
        col = (255, 150, 0) if clamped else INK_NOTE
        d.line([cx - 13, cy, cx + 13, cy], fill=col, width=2)
        d.line([cx, cy - 13, cx, cy + 13], fill=col, width=2)
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=col)

        bx, by = _badge_spot(cx, cy, panel, taken,
                             off=58 if crowd[num - 1] < 12.0 else 30)
        taken.append((bx, by))
        d.line([cx, cy, bx, by], fill=col)
        d.ellipse([bx - 15, by - 15, bx + 15, by + 15], fill=(24, 24, 28),
                  outline=col, width=2)
        t = str(num)
        tw = d.textlength(t, font=f_badge)
        d.text((bx - tw / 2, by - 11), t, fill=col, font=f_badge)

        lx = ly = ""
        hit = live.get((mod.name, n.index))
        if hit is not None:
            gx = px0 + (hit[0] + 0.5) * zoom
            gy = py0 + (hit[1] + 0.5) * zoom
            d.line([cx, cy, gx, gy], fill=INK_LIVE)
            d.line([gx - 11, gy, gx + 11, gy], fill=INK_LIVE, width=2)
            d.line([gx, gy - 11, gx, gy + 11], fill=INK_LIVE, width=2)
            d.ellipse([gx - 4, gy - 4, gx + 4, gy + 4], outline=INK_LIVE, width=2)
            lx, ly = hit

        rows.append({
            "module": mod.name, "area": mod.area, "area_name": mod.area_name,
            "image": "%s.png" % mod.name, "zoom": zoom,
            "panel_x0": px0, "panel_y0": py0,
            "panel_w": art.width, "panel_h": art.height,
            "marker_number": num, "note_index": n.index, "tag": n.tag,
            "strref": n.strref, "name": mc.strref_text(n.strref),
            "vanilla_px": "%d,%d" % p,
            "vanilla_world_x": "%.9g" % n.x, "vanilla_world_y": "%.9g" % n.y,
            "anchor_img_x": "%.1f" % cx, "anchor_img_y": "%.1f" % cy,
            "badge_img_x": "%.1f" % bx, "badge_img_y": "%.1f" % by,
            "nearest_note_px": "%.1f" % crowd[num - 1],
            "crowded": crowd[num - 1] < 12.0,
            "off_map": (not drawn),
            "live_px": ("%d,%d" % hit) if hit else "",
            "live_img_x": ("%.1f" % (px0 + (lx + 0.5) * zoom)) if hit else "",
            "live_img_y": ("%.1f" % (py0 + (ly + 0.5) * zoom)) if hit else "",
            "north_axis": cal.north_axis,
        })

    # ---- title
    d.text((PAD, 16), mod.area_name or mod.area, fill=(255, 255, 255), font=f_title)
    d.text((PAD, 54),
           "module %s   area %s   NorthAxis %d   %d map note%s   map-pixel space "
           "0..440 x 0..256, drawn here at %dx"
           % (mod.name, mod.area, cal.north_axis, len(mod.notes),
              "" if len(mod.notes) == 1 else "s", zoom),
           fill=TEXT_DIM, font=f_sub)

    # ---- legend
    lx0 = panel[2] + PAD
    d.text((lx0, py0 - 2), "MAP NOTES IN THIS AREA", fill=(255, 255, 255),
           font=_font(20, bold=True))
    y = py0 + 34
    for row in rows:
        num = row["marker_number"]
        d.ellipse([lx0, y + 1, lx0 + 26, y + 27], fill=(24, 24, 28),
                  outline=INK_NOTE, width=2)
        t = str(num)
        tw = d.textlength(t, font=f_badge)
        d.text((lx0 + 13 - tw / 2, y + 5), t, fill=INK_NOTE, font=f_badge)
        nm = row["name"] or ("<no name, tag %s>" % row["tag"])
        d.text((lx0 + 36, y + 3), nm[:38], fill=TEXT, font=f_legend)
        detail = "note #%s  tag %s  at px %s" % (row["note_index"],
                                                 (row["tag"] or "-")[:16],
                                                 row["vanilla_px"])
        d.text((lx0 + 36, y + 26), detail, fill=TEXT_DIM, font=f_small)
        flags = []
        if row["crowded"]:
            flags.append("CROWDED: another note is %s map px away - start your "
                         "line at the numbered badge, not the crosshair"
                         % row["nearest_note_px"])
        if row["off_map"]:
            flags.append("OFF-MAP: true position is outside the art, shown clamped")
        if row["live_px"]:
            flags.append("already corrected -> green cross at px %s" % row["live_px"])
        if flags:
            d.text((lx0 + 36, y + 44), "; ".join(flags)[:60], fill=INK_LIVE,
                   font=f_small)
            y += 18
        y += 50

    # ---- key
    ky = py0 + art.height - 96
    d.text((lx0, ky), "KEY", fill=(255, 255, 255), font=_font(17, bold=True))
    d.line([lx0 + 6, ky + 34, lx0 + 30, ky + 34], fill=INK_NOTE, width=2)
    d.line([lx0 + 18, ky + 22, lx0 + 18, ky + 46], fill=INK_NOTE, width=2)
    d.text((lx0 + 42, ky + 26), "authored (vanilla) position of the note",
           fill=TEXT_DIM, font=f_small)
    d.ellipse([lx0 + 4, ky + 52, lx0 + 32, ky + 80], outline=INK_RING)
    d.text((lx0 + 42, ky + 58),
           "the game's real 14x14 px note icon, to scale", fill=TEXT_DIM,
           font=f_small)

    # ---- footer: the protocol travels with the image
    fy = py0 + art.height + 12
    # NB: deliberately NOT pink/magenta. Ink detection is restricted to the map
    # panel anyway, but nothing on the page should be able to read as reviewer
    # ink if that restriction is ever relaxed.
    d.text((PAD, fy), "TO CORRECT A NOTE:  draw a MAGENTA line (#FF00FF) from "
                      "that note's marker to where the note SHOULD be, and finish "
                      "with a small circle or blob at the destination.",
           fill=(255, 235, 120), font=_font(19, bold=True))
    d.text((PAD, fy + 30),
           "The end nearest a marker says WHICH note; the far end says WHERE. "
           "One line per note, try not to let two lines cross or touch. "
           "Leave notes that are already fine untouched.",
           fill=TEXT, font=f_sub)
    d.text((PAD, fy + 54),
           "Save as PNG without resizing or cropping (the cyan corner squares are "
           "registration marks - if they survive, a resize can still be undone). "
           "Magenta is used by nothing else in this image.",
           fill=TEXT_DIM, font=f_small)
    d.text((PAD, fy + 76),
           "Green cross = where our current patch already puts the note. To change "
           "one of those, draw from the note's YELLOW marker as usual. "
           "Faint teal wash = walkable floor; a note should never sit off it.",
           fill=TEXT_DIM, font=f_small)

    # ---- fiducials, centres recorded in the index
    fids = [(INSET, INSET), (cw - 1 - INSET, INSET),
            (INSET, ch - 1 - INSET), (cw - 1 - INSET, ch - 1 - INSET)]
    h = FIDUCIAL // 2
    for fx, fy_ in fids:
        d.rectangle([fx - h, fy_ - h, fx + h, fy_ + h], fill=INK_FIDUCIAL)

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "%s.png" % mod.name)
    canvas.save(path, optimize=True)
    for row in rows:
        row["fiducials"] = " ".join("%d,%d" % f for f in fids)
        row["canvas_w"], row["canvas_h"] = cw, ch
    return path, rows


def cmd_build(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, "output", "atlas")
    zoom = ZOOM
    floor = True
    only = None
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--zoom":
            zoom = int(argv[i + 1]); i += 2; continue
        if a == "--nofloor":
            floor = False; i += 1; continue
        if a == "--only":
            only = set(argv[i + 1].split(",")); i += 2; continue
        rest.append(a); i += 1
    if rest:
        outdir = rest[0]

    live = load_live_corrections(root)
    print("live corrections known: %d" % len(live))

    resources = geomod = None
    if floor:
        import map_geometry as mg
        geomod = mg
        resources = mg.GameResources(mc.DEFAULT_GAME)

    all_rows = []
    n = 0
    for mod in mc.iter_modules():
        if not mod.notes:
            continue
        if only and mod.name not in only:
            continue
        geom = None
        if geomod is not None:
            try:
                geom = geomod.load_area_geometry(mod.area, resources)
            except Exception as exc:
                print("   (%s: no floor overlay - %s)" % (mod.name, exc))
        _path, rows = render_module(mod, outdir, live, geom, zoom)
        all_rows.extend(rows)
        n += 1
        if n % 10 == 0:
            print("   %d modules..." % n)

    index = os.path.join(outdir, "atlas_index.csv")
    fields = ["module", "area", "area_name", "image", "canvas_w", "canvas_h",
              "zoom", "panel_x0", "panel_y0", "panel_w", "panel_h", "fiducials",
              "marker_number", "note_index", "tag", "strref", "name",
              "vanilla_px", "vanilla_world_x", "vanilla_world_y",
              "anchor_img_x", "anchor_img_y", "badge_img_x", "badge_img_y",
              "nearest_note_px", "crowded", "off_map",
              "live_px", "live_img_x", "live_img_y", "north_axis"]
    if only and os.path.exists(index):
        # Rebuilding a couple of pages must not truncate the index to just
        # those pages - the ingest step reads every coordinate it needs from
        # it, so the other 88 modules would become unreadable. Merge instead:
        # the rebuilt modules' rows replace their old ones, the rest survive.
        kept = [r for r in csv.DictReader(open(index, newline="", encoding="utf-8"))
                if r["module"] not in only]
        all_rows = kept + all_rows
        all_rows.sort(key=lambda r: (r["module"], int(r["marker_number"])))
    with open(index, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    print("\nwrote %d maps and %d note rows into %s" % (n, len(all_rows), outdir))
    print("index: %s" % index)


# --------------------------------------------------------------------------
# ingest: read the reviewer's ink back out of an annotated page
# --------------------------------------------------------------------------
MIN_INK = 6            # a component smaller than this is a stray pixel
MIN_STROKE_PX = 3      # shorter than this has no readable direction
# Both are in IMAGE px, and the page is drawn at 4x, so MIN_STROKE_PX = 3 is
# under one map px. The reviewer corrects plenty of notes by only 1-2 map px,
# and at the old floor of 10 px (2.5 map px) every one of those was thrown away
# as "a dot, not a line" (2026-08-29). Direction is no longer what separates a
# correction from a confirmation: a mark whose target rounds back onto the
# authored pixel is read as "this note is already right" (see cmd_ingest), so a
# blob dabbed on the marker classifies correctly without needing a length rule.
TIP_FRACTION = 0.75    # pixels this far along the stroke count as "the tip"
ANCHOR_MAX_PX = 60     # a stroke starting further than this from any marker
SEED_STRENGTH = 100    # a component must contain a pixel this magenta to count
MERGE_GAP_PX = 14      # two components closer than this are one broken stroke
CONFIRM_TIP_PX = 4.0   # a mark reaching less than this far is a dab, not a line
# 4 image px is exactly one map px. Measured over the reviewer's own pass, the
# split is unambiguous: real short strokes reach 4.8-9.7 px from the marker,
# while dabs reach 1.7-3.8 px. A dab's one-pixel "target" is only the rounding
# of an off-centre blob, so reading it as a move would invent a correction the
# reviewer did not ask for - and, worse, would leave a wrong auto-correction
# in place where they meant "the authored position is right".


def _strength(rgb):
    """How magenta a pixel is: min(R,B) above G, 0 for anything neutral.

    A channel RELATION, not a colour distance, because a semi-opaque brush over
    dark art lands anywhere from (255,0,255) to (120,60,120). Grey art gives 0
    (R=G=B), brown/sand and teal give 0 or less (G at or above B).
    """
    r, g, b = rgb
    return min(r, b) - g


def _is_ink(rgb):
    """Weak test: could be reviewer ink. Used to grow a stroke from its seeds.

    On its own this is NOT sufficient - the map art contains dull mauve
    (e.g. 148,113,148 on Dantooine, 173,117,165 on Taris) that passes it, which
    is why real ink is identified by _strength >= SEED_STRENGTH and this test
    only decides how far the stroke around such a seed extends.
    """
    r, g, b = rgb
    return _strength(rgb) > 30 and min(r, b) > 55


def _components(mask):
    comps, rem = [], set(mask)
    while rem:
        seed = rem.pop()
        comp, stack = [seed], [seed]
        while stack:
            cx, cy = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p in rem:
                        rem.discard(p)
                        comp.append(p)
                        stack.append(p)
        comps.append(comp)
    return comps


def _merge_near(comps, gap=MERGE_GAP_PX):
    """Join components separated by less than `gap` px.

    A hand-drawn stroke often breaks into pieces: the brush lifts, or the blob
    at the far end is drawn as a second dab that does not quite touch the line.
    Those pieces are one annotation and must be read as one, or the tip lands
    in the middle of the stroke and the two halves fight over the same note.
    """
    out = [list(c) for c in comps]
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                if _bbox_gap(a, b) >= gap:
                    continue
                if _min_dist(a, b) < gap:
                    out[i] = a + b
                    del out[j]
                    merged = True
                    break
            if merged:
                break
    return out


def _min_dist(a, b):
    import numpy as np

    A = np.asarray(a, dtype=np.float64)
    B = np.asarray(b, dtype=np.float64)
    d2 = ((A[:, None, 0] - B[None, :, 0]) ** 2
          + (A[:, None, 1] - B[None, :, 1]) ** 2)
    return float(d2.min()) ** 0.5


def _bbox_gap(a, b):
    """Cheap lower bound on _min_dist, from the two bounding boxes."""
    ax = [p[0] for p in a]; ay = [p[1] for p in a]
    bx = [p[0] for p in b]; by = [p[1] for p in b]
    dx = max(0, max(min(ax) - max(bx), min(bx) - max(ax)))
    dy = max(0, max(min(ay) - max(by), min(by) - max(ay)))
    return (dx * dx + dy * dy) ** 0.5


def ink_components(im, box):
    """Reviewer strokes on a page, as merged pixel components.

    Two-level (hysteresis) detection: a blob only counts as ink if it contains
    a properly saturated magenta pixel, but once it does, the whole weakly
    magenta neighbourhood around that seed is taken as part of the stroke so
    anti-aliased edges are not clipped. Without the seed step the dull mauve in
    the map art of several planets reads as annotation.
    """
    import numpy as np

    x0, y0, pw, ph = box
    a = np.asarray(im.crop((x0, y0, x0 + pw, y0 + ph)), dtype=np.int16)
    mn = np.minimum(a[:, :, 0], a[:, :, 2])
    strength = mn - a[:, :, 1]
    weak_m = (strength > 30) & (mn > 55)
    seed_m = weak_m & (strength >= SEED_STRENGTH)

    wy, wx = np.nonzero(weak_m)
    weak = list(zip((wx + x0).tolist(), (wy + y0).tolist()))
    sy, sx = np.nonzero(seed_m)
    seeds = set(zip((sx + x0).tolist(), (sy + y0).tolist()))

    comps = [c for c in _components(weak) if seeds.intersection(c)]
    return _merge_near(comps)


def read_page(path, rows):
    """(corrections, problems) for one annotated atlas page."""
    from PIL import Image

    r0 = rows[0]
    x0, y0 = int(r0["panel_x0"]), int(r0["panel_y0"])
    pw, ph = int(r0["panel_w"]), int(r0["panel_h"])
    zoom = int(r0["zoom"])
    im = Image.open(path).convert("RGB")
    problems = []
    if im.size != (int(r0["canvas_w"]), int(r0["canvas_h"])):
        problems.append("page was resized: %s, expected %s - refusing to guess"
                        % (im.size, (r0["canvas_w"], r0["canvas_h"])))
        return [], problems

    comps = ink_components(im, (x0, y0, pw, ph))

    # every marker of every note is an anchor: crosshair, badge, and the green
    # cross of a note we already correct. All three belong to the same note, so
    # more anchors only make identification easier.
    anchors = []
    for r in rows:
        anchors.append((r, float(r["anchor_img_x"]), float(r["anchor_img_y"])))
        anchors.append((r, float(r["badge_img_x"]), float(r["badge_img_y"])))
        if r["live_img_x"]:
            anchors.append((r, float(r["live_img_x"]), float(r["live_img_y"])))

    out = []
    for comp in comps:
        if len(comp) < MIN_INK:
            continue
        import numpy as np

        A = np.array([[a[1], a[2]] for a in anchors], dtype=np.float64)
        C = np.array(comp, dtype=np.float64)
        d2 = ((A[:, None, 0] - C[None, :, 0]) ** 2
              + (A[:, None, 1] - C[None, :, 1]) ** 2)
        ai = int(d2.min(axis=1).argmin())
        dist = float(d2[ai].min()) ** 0.5
        row, ax, ay = anchors[ai][0], anchors[ai][1], anchors[ai][2]
        if dist > ANCHOR_MAX_PX:
            problems.append("a %d px mark at %s starts %.0f px from any marker - "
                            "cannot tell which note it means"
                            % (len(comp), comp[0], dist))
            continue

        far = [(((cx - ax) ** 2 + (cy - ay) ** 2) ** 0.5, cx, cy) for cx, cy in comp]
        max_d = max(f[0] for f in far)
        if max_d < MIN_STROKE_PX:
            problems.append("%s #%s (%s): the mark is only %.0f px long, so it has "
                            "no direction - draw a line, not a dot"
                            % (row["module"], row["note_index"], row["name"], max_d))
            continue
        tip = [(cx, cy) for d, cx, cy in far
               if d >= max(TIP_FRACTION * max_d, max_d - 12)]
        tx = sum(p[0] for p in tip) / float(len(tip))
        ty = sum(p[1] for p in tip) / float(len(tip))

        # image px -> map px. The marker for map pixel p was drawn at
        # panel + (p + 0.5) * zoom, so the inverse carries the same half pixel.
        mx = int(round((tx - x0) / zoom - 0.5))
        my = int(round((ty - y0) / zoom - 0.5))
        mx = min(max(mx, 0), int(mc.MAP_W) - 1)
        my = min(max(my, 0), int(mc.MAP_H) - 1)
        out.append({"row": row, "target_px": (mx, my), "anchor_dist": dist,
                    "stroke_px": max_d, "ink": len(comp),
                    "tip_img": (tx, ty),
                    "tip_dist": ((tx - ax) ** 2 + (ty - ay) ** 2) ** 0.5})

    seen = {}
    for c in out:
        key = (c["row"]["module"], c["row"]["note_index"])
        seen.setdefault(key, []).append(c)
    for key, lst in seen.items():
        if len(lst) > 1:
            problems.append("%s #%s: %d separate marks resolve to the same note "
                            "(crossed lines?) - not applied"
                            % (key[0], key[1], len(lst)))
    out = [c for c in out
           if len(seen[(c["row"]["module"], c["row"]["note_index"])]) == 1]
    return out, problems


def cmd_ingest(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = argv[0] if argv and not argv[0].startswith("--") else os.path.join(
        root, "output", "atlas-annotated")
    write = "--write" in argv
    # A page must be read against the index of the build it came from: the
    # anchors include the green cross at the note's CURRENT corrected position,
    # and that moves every time the table is rebuilt. Reading a freshly built
    # page against the original index would place those anchors where the note
    # used to be corrected to, and a stroke drawn from the green cross would
    # then be matched to the wrong note (or to none).
    index = os.path.join(src, "atlas_index.csv")
    if not os.path.exists(index):
        index = os.path.join(root, "output", "atlas", "atlas_index.csv")

    by_module = {}
    with open(index, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            by_module.setdefault(r["module"], []).append(r)

    found, problems = [], []
    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith(".png") or fn.startswith("_"):
            continue
        mod = fn[:-4]
        if mod not in by_module:
            print("skipping %s - not an atlas page" % fn)
            continue
        c, p = read_page(os.path.join(src, fn), by_module[mod])
        found.extend(c)
        problems.extend(p)

    if not found and not problems:
        print("no reviewer ink found in %s" % src)
        return 0

    print("%-12s %-4s %-24s %-11s %-11s %6s  %s"
          % ("module", "#", "note", "vanilla px", "-> target", "move", "confidence"))
    for c in sorted(found, key=lambda c: (c["row"]["module"],
                                          int(c["row"]["note_index"]))):
        r = c["row"]
        ox, oy = [int(v) for v in r["vanilla_px"].split(",")]
        mx, my = c["target_px"]
        move = ((mx - ox) ** 2 + (my - oy) ** 2) ** 0.5
        if (mx, my) == (ox, oy) or c["tip_dist"] < CONFIRM_TIP_PX:
            # The reviewer's rule (2026-08-29): a blob drawn over the vanilla
            # yellow marker, with no line leading away, means "the authored
            # position is already right". That is not a no-op - if we are
            # currently moving that note, the move has to be taken back.
            c["confirm"] = True
            print("%-12s %-4s %-24s %-11s %-11s %5s  CONFIRMED vanilla (blob on "
                  "the marker, ink %d px)"
                  % (r["module"], r["note_index"], r["name"][:24], r["vanilla_px"],
                     "-", "-", c["ink"]))
            continue
        conf = "clear" if (c["anchor_dist"] <= 12 and c["stroke_px"] >= 16) else "check"
        print("%-12s %-4s %-24s %-11s %-11s %5.1f  %s (ink %d px, stroke %.0f px, "
              "started %.0f px from the marker)"
              % (r["module"], r["note_index"], r["name"][:24], r["vanilla_px"],
                 "%d,%d" % (mx, my), move, conf, c["ink"], c["stroke_px"],
                 c["anchor_dist"]))
    for p in problems:
        print("  PROBLEM: %s" % p)

    if not write:
        print("\n(dry run - nothing written. Re-run with --write to record these "
              "as override decisions.)")
        return 0

    dec_path = os.path.join(root, "output", "note_decisions.csv")
    rows = list(csv.DictReader(open(dec_path, newline="", encoding="utf-8")))
    fields = list(rows[0].keys())
    by_key = {(r["module"], str(r["note_index"])): r for r in rows}
    stamp = "2026-08-29 user (atlas annotation, full pass)"
    added = updated = 0
    for c in found:
        r = c["row"]
        key = (r["module"], str(r["note_index"]))
        confirm = c.get("confirm")
        if confirm:
            reason = ("blob drawn over the vanilla marker on the atlas: reviewer "
                      "confirms the authored position, do not move this note")
        else:
            reason = ("hand-placed on the atlas: magenta mark %.0f px from the "
                      "marker, target map px %d,%d"
                      % (c["anchor_dist"], *c["target_px"]))
        row = by_key.get(key)
        if row is None:
            row = {f: "" for f in fields}
            row.update({"module": r["module"], "note_index": r["note_index"],
                        "name": r["name"]})
            rows.append(row)
            by_key[key] = row
            added += 1
        else:
            updated += 1
        row["decision"] = "reject" if confirm else "override"
        row["target_px"] = "" if confirm else "%d,%d" % c["target_px"]
        row["decided"] = stamp
        row["reason"] = reason
    with open(dec_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["module"], int(r["note_index"]))))
    print("\nwrote %s: %d new, %d updated" % (dec_path, added, updated))
    print("next: python tools/note_corrections.py finalize ../output/note_corrections.csv")
    return 0


COMMANDS = {"build": cmd_build, "ingest": cmd_ingest}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
