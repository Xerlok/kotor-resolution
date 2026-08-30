"""Check every ingested atlas target against the area's walkable floor.

The annotation protocol says a note must never sit off walkable floor. The
ingest reader is purely geometric - it knows where the ink points, not whether
that spot is a place you can stand - so this runs the resolved targets past the
same room polygons `map_note_propose` uses and reports any that miss.

    python tools/atlas_validate_targets.py <annotated-dir>
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_calibration as mc
import map_geometry as mg
import map_note_atlas as mna


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = argv[0]
    index = os.path.join(root, "output", "atlas", "atlas_index.csv")
    by_module = {}
    with open(index, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            by_module.setdefault(r["module"], []).append(r)

    resources = mg.GameResources(mc.DEFAULT_GAME)
    off, on, nogeom = [], 0, []
    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith(".png"):
            continue
        mod_name = fn[:-4]
        if mod_name not in by_module:
            continue
        corr, _ = mna.read_page(os.path.join(src, fn), by_module[mod_name])
        if not corr:
            continue
        module = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules",
                                             mod_name + ".rim"))
        cal = module.calibration
        geom = mg.load_area_geometry(module.area, resources)
        if geom is None or not geom.rooms:
            nogeom.append(mod_name)
            continue
        for c in corr:
            wx, wy = cal.to_world(*c["target_px"])
            if geom.on_floor(wx, wy):
                on += 1
            else:
                room, d = geom.nearest_room(wx, wy)
                off.append((mod_name, c["row"]["note_index"], c["row"]["name"],
                            c["target_px"], d, room.name if room else "-"))

    print("on walkable floor: %d" % on)
    print("no room geometry available: %s" % (", ".join(nogeom) or "none"))
    print("OFF walkable floor: %d" % len(off))
    for m, ni, name, px, d, room in sorted(off, key=lambda t: -t[4]):
        print("  %-12s #%-4s %-26s target %-9s %6.2f world units from %s"
              % (m, ni, name[:26], "%d,%d" % px, d, room))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
