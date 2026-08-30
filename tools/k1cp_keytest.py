"""Does a data mod move a map note out from under our note table?

Our exe table matches a note by its world position as float32 - see
`note_corrections.f32` and the 16-byte entry layout (oldX, oldY, newX, newY).
So any mod that moves a note by even one float bit makes our correction stop
matching, and that note silently falls back to its vanilla position. This tool
turns "we assume graceful degradation" into a number.

Two things make it a different job from `note_corrections.py finalize`:

  1. **Resource priority.** `map_calibration.iter_modules` reads `modules/*.rim`
     only. That is right for deriving the shipped table from a clean install,
     but it is NOT what the engine loads: HoloPatcher/TSLPatcher mods install
     `modules/<name>.mod`, and a `.mod` wins over the `.rim` of the same name.
     Reading `.rim` against a modded install would report zero changes no matter
     what the mod did - a false pass. This tool reads `.mod` first.
  2. **It never writes.** `finalize` has no --game flag and rewrites
     `output/note_corrections.csv` as a side effect; pointing that at a modded
     install would overwrite the shipped 250-correction table.

Usage:
    python tools/k1cp_keytest.py <modded-game-dir> [--baseline <clean-game-dir>]
                                                   [--json out.json]

Baseline defaults to `map_calibration.DEFAULT_GAME`.
"""

from __future__ import annotations

import os
import sys
import csv
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import map_calibration as mc
from note_corrections import f32

from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.erf import read_erf
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.type import ResourceType

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED_CSV = os.path.join(_ROOT, "output", "note_corrections.csv")


def _read_container(path):
    """A .mod is an ERF, a .rim is a RIM; both iterate resources the same way."""
    reader = read_erf if path.lower().endswith(".mod") else read_rim
    try:
        return reader(path)
    except Exception:
        return None


def notes_from_container(path):
    """Map notes in one module file: the WaypointList entries the game draws.

    HasMapNote - not MapNoteEnabled - is what makes a note render
    (map_calibration.load_module says the same, and gives ebo_m12aa as the
    case that proves it: 33 waypoints enabled, only 7 drawn).
    """
    con = _read_container(path)
    if con is None:
        return None
    git = None
    for res in con:
        if res.restype == ResourceType.GIT:
            git = res.data
    if git is None:
        return None
    try:
        git_gff = read_gff(git)
    except Exception:
        return None

    lst = git_gff.root.acquire("WaypointList", None)
    if lst is None:
        return []
    out = []
    for i in range(len(lst)):
        st = lst.at(i)
        if not st.acquire("HasMapNote", 0):
            continue
        x, y = st.acquire("XPosition", None), st.acquire("YPosition", None)
        if x is None or y is None:
            continue
        mn = st.acquire("MapNote", None)
        out.append({
            "index": i,
            "tag": str(st.acquire("Tag", "") or ""),
            "strref": getattr(mn, "stringref", -1) if mn is not None else -1,
            "x": f32(x), "y": f32(y),
        })
    return out


def module_notes(game_dir):
    """{module: [note, ...]} honouring engine priority: .mod beats .rim.

    Returns the notes plus the set of modules the mod served from a .mod, so
    the caller can say how much of the game the mod actually touched.
    """
    mod_dir = os.path.join(game_dir, "modules")
    bases = {}
    for path in glob.glob(os.path.join(mod_dir, "*.rim")):
        name = os.path.basename(path)
        if name.endswith("_s.rim"):
            continue
        bases[name[:-4]] = path
    overridden = set()
    for path in glob.glob(os.path.join(mod_dir, "*.mod")):
        base = os.path.basename(path)[:-4]
        if base.endswith("_s"):
            continue
        bases[base] = path                  # a .mod wins over the .rim
        overridden.add(base)

    notes = {}
    for base, path in sorted(bases.items()):
        n = notes_from_container(path)
        if n:
            notes[base] = n
    return notes, overridden


def compare(baseline, modded):
    """Per-note verdict, keyed the way the exe keys it: (f32 x, f32 y)."""
    moved, added, removed, same = [], [], [], 0
    for base, notes in sorted(modded.items()):
        old = {n["index"]: n for n in baseline.get(base, [])}
        new = {n["index"]: n for n in notes}
        for i, n in sorted(new.items()):
            o = old.get(i)
            if o is None:
                added.append((base, i, n["tag"], n["x"], n["y"]))
            elif (o["x"], o["y"]) != (n["x"], n["y"]):
                moved.append((base, i, n["tag"],
                              (o["x"], o["y"]), (n["x"], n["y"])))
            else:
                same += 1
        for i, o in sorted(old.items()):
            if i not in new:
                removed.append((base, i, o["tag"], o["x"], o["y"]))
    for base, notes in sorted(baseline.items()):
        if base not in modded:
            for o in notes:
                removed.append((base, o["index"], o["tag"], o["x"], o["y"]))
    return moved, added, removed, same


def shipped_keys(path=SHIPPED_CSV):
    """The 250 keys actually burned into the exe table."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (f32(row["old_world_x"]), f32(row["old_world_y"]))
            out[key] = (row["module"], row["note_index"], row["name"])
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    modded = argv[0]
    baseline_dir = mc.DEFAULT_GAME
    json_out = None
    if "--baseline" in argv:
        baseline_dir = argv[argv.index("--baseline") + 1]
    if "--json" in argv:
        json_out = argv[argv.index("--json") + 1]

    base_notes, base_over = module_notes(baseline_dir)
    mod_notes, mod_over = module_notes(modded)

    print("baseline : %s" % baseline_dir)
    print("           %d modules with notes, %d notes, %d served from .mod"
          % (len(base_notes), sum(len(v) for v in base_notes.values()), len(base_over)))
    print("modded   : %s" % modded)
    print("           %d modules with notes, %d notes, %d served from .mod"
          % (len(mod_notes), sum(len(v) for v in mod_notes.values()), len(mod_over)))
    if not mod_over:
        print("\nWARNING: the modded install has no modules/*.mod at all. Either the")
        print("mod installed nothing into modules/, or it did not run. A pass here")
        print("would be meaningless - check the install before trusting this.")

    moved, added, removed, same = compare(base_notes, mod_notes)
    print("\nnotes unchanged: %d" % same)
    print("notes moved:     %d   <- these break our table key" % len(moved))
    print("notes added:     %d   (harmless: we simply do not correct them)" % len(added))
    print("notes removed:   %d" % len(removed))

    for base, i, tag, o, n in moved:
        print("   MOVED  %-12s #%-3d %-24s (%.4f, %.4f) -> (%.4f, %.4f)"
              % (base, i, tag[:24], o[0], o[1], n[0], n[1]))
    for base, i, tag, x, y in added:
        print("   ADDED  %-12s #%-3d %-24s (%.4f, %.4f)" % (base, i, tag[:24], x, y))
    for base, i, tag, x, y in removed:
        print("   GONE   %-12s #%-3d %-24s (%.4f, %.4f)" % (base, i, tag[:24], x, y))

    # The number that actually matters: of the 250 corrections in the exe, how
    # many still find their note?
    ship = shipped_keys()
    live = set()
    for notes in mod_notes.values():
        for n in notes:
            live.add((n["x"], n["y"]))
    lost = sorted((v for k, v in ship.items() if k not in live))
    print("\nshipped corrections: %d" % len(ship))
    print("still matching:      %d" % (len(ship) - len(lost)))
    print("stop matching:       %d   <- silently fall back to vanilla" % len(lost))
    for mod_name, idx, name in lost:
        print("   LOST   %-12s #%-3s %s" % (mod_name, idx, name))

    if json_out:
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump({
                "baseline": baseline_dir, "modded": modded,
                "modules_from_mod": sorted(mod_over),
                "notes_unchanged": same,
                "moved": moved, "added": added, "removed": removed,
                "shipped_corrections": len(ship), "lost": lost,
            }, fh, indent=1)
        print("\nwrote %s" % json_out)

    return 1 if moved or lost else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
