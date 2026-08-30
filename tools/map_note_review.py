"""Review surface for the map-note proposals (Phase 2b).

`map_note_propose.py` decides WHAT to propose; this module makes the proposals
judgeable. Whole-map renders are too coarse to tell whether a marker covers the
thing it names, so this crops a zoomed tile per proposal and tiles them into
contact sheets.

Commands
--------
  triage [out.csv]
        Split the proposals into "self-evident" and "needs a human eye", with the
        reason for each. Writes the worklist.

  crops [outdir] [--all]
        One zoomed PNG per flagged proposal (--all: per proposal, full stop).

  sheets [outdir] [--all] [--per N]
        Contact sheets of the same crops, N per sheet (default 6), grouped by
        triage class so like is compared with like.

Triage classes that need a human eye
------------------------------------
  clamp                     - no good answer existed; the fallback was used
  low confidence            - the proposal rule itself flagged it
  position-only match       - snapped to an exit whose NAME did not match
  big move                  - >=15 px; right or wrong, it is a visible change
  recentred an on-floor note - the note was already on valid floor, so BioWare
                              may have placed it deliberately off-centre
Everything else is a short move onto an exactly-name-matched anchor.
"""

from __future__ import annotations

import os
import sys
import csv
import math

import map_calibration as mc
import map_geometry as mg
import map_note_propose as mp

BIG_MOVE_PX = 15.0
RECENTRE_PX = 10.0


# --------------------------------------------------------------------------
def classify(prop):
    """Triage class for one Proposal. 'auto' means no human eye needed."""
    if prop.rule in ("none",) or prop.move_px < mp.MIN_MOVE_PX:
        return None
    # The proposal pass itself asked for a human: a different room than vanilla,
    # a big move, an ambiguous door. These are held out of the exe table until
    # decided, so they come first.
    if getattr(prop, "review", False):
        if prop.rule == "door_room":
            # No ">" or other path-illegal characters: the class name becomes a
            # sheet filename on Windows.
            return "green door into next room"
        return "flagged: different room or big move"
    if prop.rule in ("clamp_to_map", "clamp_to_floor"):
        return "clamp"
    if prop.confidence == "low":
        return "low confidence"
    if "matched on position, not name" in prop.reason:
        return "position-only match"
    if prop.move_px >= BIG_MOVE_PX:
        return "big move"
    if (prop.rule == "room_centre" and prop.move_px > RECENTRE_PX
            and "off walkable floor" not in prop.reason):
        return "recentred an on-floor note"
    return "auto"


def iter_flagged(game=mc.DEFAULT_GAME, include_auto=False):
    """Yield (mod, geom, prop, klass) for proposals needing review."""
    for mod, props, geom in mp._iter_proposals(game):
        for prop in props:
            klass = classify(prop)
            if klass is None:
                continue
            if klass == "auto" and not include_auto:
                continue
            yield mod, geom, prop, klass


# --------------------------------------------------------------------------
def cmd_triage(argv):
    out_csv = argv[0] if argv and not argv[0].startswith("--") else None
    counts, rows = {}, []
    for mod, _geom, prop, klass in iter_flagged(include_auto=True):
        counts[klass] = counts.get(klass, 0) + 1
        rows.append({
            "module": mod.name, "note_index": prop.note.index,
            "tag": prop.note.tag, "name": mc.strref_text(prop.note.strref),
            "triage": klass, "rule": prop.rule, "confidence": prop.confidence,
            "move_px": "%.1f" % prop.move_px,
            "old_px": "%d,%d" % prop.old_px, "new_px": "%d,%d" % prop.new_px,
            "new_world_x": "%.6f" % prop.new_x, "new_world_y": "%.6f" % prop.new_y,
            "reason": prop.reason,
            # left blank for the reviewer to fill in
            "decision": "", "target_px": "", "note": "",
        })
    total = len(rows)
    eyes = total - counts.get("auto", 0)
    print("proposals: %d    self-evident: %d    need a human eye: %d (%.0f%%)"
          % (total, counts.get("auto", 0), eyes, 100.0 * eyes / total))
    for k in sorted(counts, key=lambda k: -counts[k]):
        if k != "auto":
            print("   %-28s %3d" % (k, counts[k]))
    print("   %-28s %3d" % ("(self-evident)", counts.get("auto", 0)))
    if out_csv:
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["triage"] == "auto",
                                                    -float(r["move_px"]))))
        print("\nwrote %s (%d rows; fill in decision/target_px/note)" % (out_csv, len(rows)))


# --------------------------------------------------------------------------
def _font(size):
    from PIL import ImageFont
    for nm in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nm, size)
        except Exception:
            pass
    return ImageFont.load_default()


CROP_W = 460          # output tile width in px, before the caption bar
MIN_WINDOW = 56.0     # smallest map-pixel window, so a 14 px icon stays legible
CAPTION_H = 56


def crop_proposal(mod, geom, prop, klass, out_size=CROP_W):
    """A zoomed before/after tile for one proposal, with a caption."""
    from PIL import Image, ImageDraw

    cal = mod.calibration
    tex = mc.load_map_texture(mod.area)
    base = Image.new("RGB", (int(mc.MAP_W), int(mc.MAP_H)), (0, 0, 0))
    if tex is not None:
        base.paste(tex, (0, 0))

    # window: contains both positions plus margin, never tighter than MIN_WINDOW
    ox, oy = prop.old_px
    nx, ny = prop.new_px
    cx, cy = (ox + nx) / 2.0, (oy + ny) / 2.0
    span = max(abs(nx - ox), abs(ny - oy)) + 34.0
    win = max(MIN_WINDOW, span)
    zoom = out_size / win
    x0, y0 = cx - win / 2.0, cy - win / 2.0

    # The crop can run off the map (off-map notes are exactly what we review),
    # so paste the map into a padded canvas rather than clamping the window.
    pad = int(mc.MAP_W)
    padded = Image.new("RGB", (int(mc.MAP_W) + 2 * pad, int(mc.MAP_H) + 2 * pad),
                       (26, 26, 30))
    padded.paste(base, (pad, pad))
    left, top = int(round(x0)) + pad, int(round(y0)) + pad
    side = int(round(win))
    tile = padded.crop((left, top, left + side, top + side)) \
                 .resize((out_size, out_size), Image.NEAREST)

    canvas = Image.new("RGB", (out_size, out_size + CAPTION_H), (18, 18, 22))
    canvas.paste(tile, (0, 0))
    d = ImageDraw.Draw(canvas)

    def P(px, py):
        return (px - x0) * zoom, (py - y0) * zoom

    def Pw(wx, wy):
        px, py = cal.to_pixel(wx, wy, integer=False)
        return P(px + 0.5, py + 0.5)

    if geom is not None:
        for room in geom.rooms:
            for t in room.tris:
                d.polygon([Pw(*t[0]), Pw(*t[1]), Pw(*t[2])], outline=(0, 78, 96))
    for _lst, _tag, wx, wy in mod.objects:
        x, y = Pw(wx, wy)
        if -8 <= x <= out_size + 8 and -8 <= y <= out_size + 8:
            d.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill=(0, 210, 210))
    for tr in mod.transitions:
        x, y = Pw(tr.x, tr.y)
        if -10 <= x <= out_size + 10 and -10 <= y <= out_size + 10:
            d.rectangle([x - 4, y - 4, x + 4, y + 4], outline=(130, 130, 255))

    # map boundary, so "off the map" is visible
    bx0, by0 = P(0, 0)
    bx1, by1 = P(mc.MAP_W, mc.MAP_H)
    d.rectangle([bx0, by0, bx1, by1], outline=(90, 70, 40))

    # current position
    x, y = P(ox + 0.5, oy + 0.5)
    r = 3.5 * zoom / 2
    d.line([x - r * 1.8, y, x + r * 1.8, y], fill=(255, 45, 45), width=2)
    d.line([x, y - r * 1.8, x, y + r * 1.8], fill=(255, 45, 45), width=2)
    d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 45, 45), width=2)
    # proposal, with the game's real 14 px icon to scale
    x2, y2 = P(nx + 0.5, ny + 0.5)
    d.line([x, y, x2, y2], fill=(0, 255, 120), width=2)
    d.ellipse([x2 - 7 * zoom, y2 - 7 * zoom, x2 + 7 * zoom, y2 + 7 * zoom],
              outline=(255, 255, 255))
    d.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], outline=(0, 255, 120), width=3)

    small, tiny = _font(15), _font(12)
    name = mc.strref_text(prop.note.strref) or prop.note.tag
    d.text((6, out_size + 4), "%s  #%d  %s" % (mod.name, prop.note.index, name),
           fill=(255, 235, 140), font=small)
    d.text((6, out_size + 22), "%s / %s / %.0f px   [%s]"
           % (prop.rule, prop.confidence, prop.move_px, klass),
           fill=(150, 220, 170), font=tiny)
    d.text((6, out_size + 37), prop.reason[:96], fill=(150, 150, 155), font=tiny)
    return canvas


def cmd_crops(argv):
    include_auto = "--all" in argv
    argv = [a for a in argv if not a.startswith("--")]
    outdir = argv[0] if argv else os.path.join("output", "review-crops")
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for mod, geom, prop, klass in iter_flagged(include_auto=include_auto):
        img = crop_proposal(mod, geom, prop, klass)
        img.save(os.path.join(outdir, "%s_%03d.png" % (mod.name, prop.note.index)))
        n += 1
    print("wrote %d crops into %s" % (n, outdir))


def cmd_sheets(argv):
    from PIL import Image, ImageDraw

    include_auto = "--all" in argv
    per = 6
    if "--per" in argv:
        i = argv.index("--per")
        per = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    argv = [a for a in argv if not a.startswith("--")]
    outdir = argv[0] if argv else os.path.join("output", "review-sheets")
    os.makedirs(outdir, exist_ok=True)

    groups = {}
    for mod, geom, prop, klass in iter_flagged(include_auto=include_auto):
        groups.setdefault(klass, []).append((mod, geom, prop, klass))

    cols = 3
    written = []
    for klass, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda it: -it[2].move_px)
        slug = klass.replace(" ", "-")
        for page in range(0, len(items), per):
            chunk = items[page:page + per]
            rows = int(math.ceil(len(chunk) / float(cols)))
            tw, th = CROP_W, CROP_W + CAPTION_H
            head = 30
            sheet = Image.new("RGB", (cols * tw + (cols + 1) * 6,
                                      head + rows * th + (rows + 1) * 6), (12, 12, 15))
            d = ImageDraw.Draw(sheet)
            d.text((8, 7), "%s  -  %d..%d of %d   (red=current, green=proposed, "
                           "white ring=real 14px icon, teal=walkable floor, blue=exit)"
                   % (klass, page + 1, page + len(chunk), len(items)),
                   fill=(230, 230, 230), font=_font(15))
            for i, (mod, geom, prop, kl) in enumerate(chunk):
                img = crop_proposal(mod, geom, prop, kl)
                cx = 6 + (i % cols) * (tw + 6)
                cy = head + 6 + (i // cols) * (th + 6)
                sheet.paste(img, (cx, cy))
            path = os.path.join(outdir, "%s_%d.png" % (slug, page // per + 1))
            sheet.save(path)
            written.append(path)
    print("wrote %d sheets into %s" % (len(written), outdir))
    for p in written:
        print("   ", p)


COMMANDS = {"triage": cmd_triage, "crops": cmd_crops, "sheets": cmd_sheets}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
