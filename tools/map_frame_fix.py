"""Hide the Area Map's baked-in frame line by growing LBL_Map over it.

THE PROBLEM
-----------
The Area Map screen shows a thin light-blue line along the top, left and right
of the map viewport, and none along the bottom.

That line is not drawn by the GUI: LBL_Map has no BORDER. It is a 1-pixel
border baked into the panel's background art (`lbl_map`), which vanilla draws
around a 640x480 panel where one art pixel is one screen pixel. We stretch that
art across 2560x1600, so the same 1-px line becomes 4 px on the left, 2 px on
top and 2 px on the right - thick enough to read as a stray line rather than a
frame. Measured on the user's 2560x1600 screenshot:

    left    x 376..379   (4 px)
    top     y 391..392   (2 px)
    right   x 2140..2141 (2 px)
    bottom  y 1246       present but at ~5% brightness (0,7,33) - invisible

THE FIX
-------
Grow the box until the map's own black background covers the line on all four
sides - which is exactly why the bottom edge looked clean to begin with, its
edge already reached the art's bottom line.

    LBL_Map  (380, 393, 1760, 853)  ->  (376, 389, 1768, 861)

Grow every side by the SAME amount. The first attempt grew them unevenly
(4 left, 2 up, 2 right, 0 down), which moved the box centre up-left by ~1 px;
the map content is centred in the box, so it stopped covering the art's bottom
line and that line became visible instead. Equal growth keeps the centre at
(1260, 819.5), identical to the original box, so nothing moves.

That is +8 px in each dimension, a 0.45% / 0.94% change in the draw box - far
too small to see, and the map art and every marker scale together because they
are all placed inside this box.

Safe to change: nothing hardcodes the box. The exe binds "LBL_Map" by name at
0x694D50 and reads its extent at runtime, so the map simply fills the new box.

    python tools/map_frame_fix.py plan  [GUI]
    python tools/map_frame_fix.py apply [GUI]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# gff_writer does `from . import gff`, so it only imports as part of the tools
# package - hence the project root on the path and the package-qualified import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backup_paths
from tools import gff, gff_writer

LIVE_GUI = (r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
            r"\Override\map.gui")
CONTROL = "LBL_Map"
# The vanilla-scaled original, and the first (asymmetric) attempt at this fix.
KNOWN_EXTENTS = {(380, 393, 1760, 853), (376, 391, 1766, 855)}
OLD_EXTENT = (380, 393, 1760, 853)
# Grow every side by 4 px. Growing them by DIFFERENT amounts (the first attempt:
# 4 left, 2 up, 2 right, 0 down) moves the box centre, and the map content is
# centred in the box - so it shifted up-left and stopped covering the art's
# bottom frame line, which then became visible. This keeps the centre exactly
# where it was: x (376+2144)/2 = 1260 and y (389+1250)/2 = 819.5, both identical
# to the original box, so nothing moves and all four lines are covered.
NEW_EXTENT = (376, 389, 1768, 861)


def _val(v):
    return v.value if hasattr(v, "value") else v


def find_control(top, tag):
    for c in _val(top.fields.get("CONTROLS")) or []:
        if _val(c.fields.get("TAG")) == tag:
            return c
    return None


def read_extent(ctrl):
    ef = _val(ctrl.fields["EXTENT"]).fields
    return tuple(int(_val(ef[k])) for k in ("LEFT", "TOP", "WIDTH", "HEIGHT"))


def set_extent(ctrl, extent):
    ef = _val(ctrl.fields["EXTENT"]).fields
    for k, v in zip(("LEFT", "TOP", "WIDTH", "HEIGHT"), extent):
        field = ef[k]
        if hasattr(field, "value"):
            field.value = int(v)
        else:
            ef[k] = int(v)


def plan(path):
    g = gff.load(path)
    ctrl = find_control(g.top, CONTROL)
    if ctrl is None:
        raise SystemExit("%s has no %s control" % (path, CONTROL))
    cur = read_extent(ctrl)
    print("file:    %s" % path)
    print("%s extent now: %s" % (CONTROL, (cur,)))
    if cur == NEW_EXTENT:
        print("already patched - nothing to do")
        return g, ctrl, False
    if cur not in KNOWN_EXTENTS:
        print("WARNING: expected %s, found %s. The frame line is measured "
              "against the expected layout, so the new extent below may not "
              "line up. Re-measure from a screenshot before applying."
              % (OLD_EXTENT, cur))
    print("%s extent new: %s" % (CONTROL, (NEW_EXTENT,)))
    print("  grows %d px left, %d px up, %d px right, %d px down"
          % (cur[0] - NEW_EXTENT[0],
             cur[1] - NEW_EXTENT[1],
             (NEW_EXTENT[0] + NEW_EXTENT[2]) - (cur[0] + cur[2]),
             (NEW_EXTENT[1] + NEW_EXTENT[3]) - (cur[1] + cur[3])))
    return g, ctrl, True


def apply(path):
    g, ctrl, needed = plan(path)
    if not needed:
        return 0
    backup = backup_paths.make_backup(path, ".pre-mapframefix-backup")
    print("\nbacked up to %s" % backup)

    set_extent(ctrl, NEW_EXTENT)
    with open(path, "wb") as fh:
        fh.write(gff_writer.dumps(g))

    # verify from disk: re-parse and check every control, not just ours - a
    # writer bug would show up as some other extent changing.
    written = gff.load(path)
    got = read_extent(find_control(written.top, CONTROL))
    ok = got == NEW_EXTENT
    print("readback %s extent: %s  %s"
          % (CONTROL, (got,), "OK" if ok else "MISMATCH"))
    before = {t: e for t, e in _all_extents(g.top)}
    after = {t: e for t, e in _all_extents(written.top)}
    for tag in sorted(before):
        if before[tag] != after.get(tag):
            print("  CHANGED unexpectedly: %s %s -> %s"
                  % (tag, before[tag], after.get(tag)))
            ok = False
    if not ok:
        print("\nVERIFY FAILED - restore with:\n  copy \"%s\" \"%s\""
              % (backup, path))
        return 1
    print("all other controls unchanged")
    print("\nNOT yet confirmed in game. Open the Area Map and check the top, "
          "left and right edges of the map box.")
    print("Revert with:  copy \"%s\" \"%s\"" % (backup, path))
    return 0


def _all_extents(top):
    for c in _val(top.fields.get("CONTROLS")) or []:
        yield _val(c.fields.get("TAG")), read_extent(c)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("plan", "apply"):
        print(__doc__)
        raise SystemExit(2)
    target = sys.argv[2] if len(sys.argv) > 2 else LIVE_GUI
    if sys.argv[1] == "plan":
        plan(target)
        raise SystemExit(0)
    raise SystemExit(apply(target))
