"""Write a module `.git` with one or more map notes moved to chosen map pixels.

Used for the Phase 1a test (does a `.git` data edit reach an existing save?) and
as the prototype of the data-edit delivery route.

Everything is verified before the file is written:
  - PyKotor round-trips these `.git` files BYTE-IDENTICALLY (checked on
    m14ad.git and m01aa.git), so the output differs from the original only in
    the floats this tool sets. The byte-difference count is reported.
  - the new world position is re-projected through the calibration and must land
    on exactly the requested map pixel.

The output file is named after the .git's own resref, which is the AREA resref
(`m14ad.git`), NOT the module name - that is the name the engine looks up, and
the name the save-game cache uses too.

  python tools/make_git_edit.py <module> <note> <px> <py> [<note> <px> <py> ...]
                               [--out DIR]

`<note>` is a WaypointList index or a note tag. Default output dir is
`output/git-edits/<module>/`. Nothing is installed anywhere - copy the file to
the game's Override (or into a .mod) yourself.
"""

from __future__ import annotations

import os
import sys

import map_calibration as mc
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.gff import read_gff, bytes_gff
from pykotor.resource.type import ResourceType


def _load_git(game, module):
    path = os.path.join(game, "modules", module + ".rim")
    rim = read_rim(path)
    for res in rim:
        if res.restype == ResourceType.GIT:
            return str(res.resref), res.data
    raise SystemExit("no .git in %s" % path)


def edit_git(module, edits, out_dir, game=mc.DEFAULT_GAME):
    """edits: [(note_ident, target_px, target_py)]. Returns the written path."""
    mod = mc.load_module(os.path.join(game, "modules", module + ".rim"))
    if mod is None:
        raise SystemExit("no map data for %s" % module)
    cal = mod.calibration
    git_resref, original = _load_git(game, module)
    gff = read_gff(original)
    waypoints = gff.root.acquire("WaypointList", None)
    if waypoints is None:
        raise SystemExit("%s has no WaypointList" % module)

    print("%s (area %s, NorthAxis %d) - editing %s.git"
          % (module, mod.area, cal.north_axis, git_resref))
    applied = []
    for ident, px, py in edits:
        note = None
        for n in mod.notes:
            if str(n.index) == str(ident) or n.tag.lower() == str(ident).lower():
                note = n
                break
        if note is None:
            raise SystemExit("no map note %r in %s (have: %s)"
                             % (ident, module,
                                ", ".join("%d:%s" % (n.index, n.tag) for n in mod.notes)))
        nx, ny = cal.to_world(px, py)
        check = cal.to_pixel(nx, ny)
        if check != (int(px), int(py)):
            raise SystemExit("round-trip failed for %s: asked px%s, got px%s"
                             % (ident, (px, py), check))
        st = waypoints.at(note.index)
        st.set_single("XPosition", nx)
        st.set_single("YPosition", ny)
        old_px = cal.to_pixel(note.x, note.y)
        print("   #%-3d %-18s %-24s px%s -> px%s   world (%.4f, %.4f) -> (%.4f, %.4f)"
              % (note.index, note.tag, mc.strref_text(note.strref, game),
                 old_px, (int(px), int(py)), note.x, note.y, nx, ny))
        applied.append((note, nx, ny, (int(px), int(py))))

    data = bytes_gff(gff)
    if len(data) != len(original):
        print("   NOTE: size changed %d -> %d bytes" % (len(original), len(data)))
    diff = sum(1 for a, b in zip(data, original) if a != b) + abs(len(data) - len(original))
    print("   %d bytes differ from the original .git (at most 8 per note moved)" % diff)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, git_resref + ".git")
    with open(path, "wb") as fh:
        fh.write(data)

    # Verify by reading the file back off disk, not the object in memory. The
    # test is the projected PIXEL, not the float: a GFF stores float32, so the
    # value read back is the float32 rounding of what was written.
    verify = read_gff(open(path, "rb").read())
    vw = verify.root.acquire("WaypointList", None)
    for note, nx, ny, target in applied:
        st = vw.at(note.index)
        gx, gy = float(st.acquire("XPosition", None)), float(st.acquire("YPosition", None))
        got = cal.to_pixel(gx, gy)
        ok = got == target and abs(gx - nx) < 1e-3 and abs(gy - ny) < 1e-3
        print("   verify #%-3d %-18s world (%.4f, %.4f) -> px%s  %s"
              % (note.index, note.tag, gx, gy, got, "OK" if ok else "MISMATCH"))
        if not ok:
            raise SystemExit("verification failed")
    print("   wrote %s (%d bytes)" % (path, len(data)))
    return path


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    out_dir = None
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    module, rest = argv[0], argv[1:]
    if len(rest) % 3:
        print("each edit needs <note> <px> <py>")
        return 2
    edits = [(rest[i], int(rest[i + 1]), int(rest[i + 2])) for i in range(0, len(rest), 3)]
    edit_git(module, edits,
             out_dir or os.path.join("output", "git-edits", module))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
