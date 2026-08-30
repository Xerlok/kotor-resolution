"""Prove the K1CP key test is not a false pass.

k1cp_keytest reported 0 map notes moved. K1CP's changes.ini demonstrably edits
WaypointList XPosition/YPosition. Both can be true only if the waypoints it
moves are not map notes (HasMapNote=0). This checks that directly: compare
EVERY waypoint, note or not, vanilla vs modded.

If total moved == 0 the reader is blind and the pass is worthless.
If total moved > 0 while note moved == 0, the pass is real and explained.
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import k1cp_keytest as kt
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODDED = os.path.join(_ROOT, "staging", "k1cp-testinstall")


def waypoints(path):
    """[(index, x, y, hasmapnote)] from a container's GIT, or None."""
    con = kt._read_container(path)
    if con is None:
        return None
    git = None
    for res in con:
        if res.restype == ResourceType.GIT:
            git = res.data
    if git is None:
        return None
    try:
        g = read_gff(git)
    except Exception:
        return None
    lst = g.root.acquire("WaypointList", None)
    if lst is None:
        return []
    out = []
    for i in range(len(lst)):
        st = lst.at(i)
        x, y = st.acquire("XPosition", None), st.acquire("YPosition", None)
        if x is None or y is None:
            continue
        out.append((i, float(x), float(y), int(st.acquire("HasMapNote", 0) or 0)))
    return out


def main(argv):
    """usage: python tools/k1cp_verify.py [modded-game-dir] [--baseline clean-dir]"""
    global VANILLA, MODDED
    modded_game = argv[0] if argv and not argv[0].startswith("-") else DEFAULT_MODDED
    baseline_game = kt.mc.DEFAULT_GAME
    if "--baseline" in argv:
        baseline_game = argv[argv.index("--baseline") + 1]
    VANILLA = os.path.join(baseline_game, "modules")
    MODDED = os.path.join(modded_game, "modules")
    print("baseline: %s" % VANILLA)
    print("modded  : %s\n" % MODDED)

    bases = {}
    for p in glob.glob(os.path.join(VANILLA, "*.rim")):
        n = os.path.basename(p)
        if not n.endswith("_s.rim"):
            bases[n[:-4]] = p

    moved_any = moved_notes = compared = mods_read = 0
    examples = []
    for base, vpath in sorted(bases.items()):
        mpath = os.path.join(MODDED, base + ".mod")
        if not os.path.exists(mpath):
            mpath = os.path.join(MODDED, base + ".rim")
        else:
            mods_read += 1
        v, m = waypoints(vpath), waypoints(mpath)
        if v is None or m is None:
            continue
        vd = {i: (x, y, h) for i, x, y, h in v}
        for i, x, y, h in m:
            if i not in vd:
                continue
            compared += 1
            ox, oy, oh = vd[i]
            if (ox, oy) != (x, y):
                moved_any += 1
                if h or oh:
                    moved_notes += 1
                if len(examples) < 8:
                    examples.append("%-14s wp#%-3d (%.3f, %.3f) -> (%.3f, %.3f)  HasMapNote %d->%d"
                                    % (base, i, ox, oy, x, y, oh, h))

    print("modules read from a K1CP .mod : %d" % mods_read)
    print("waypoints compared            : %d" % compared)
    print("waypoints MOVED by K1CP       : %d" % moved_any)
    print("  of those, map notes         : %d" % moved_notes)
    print()
    for e in examples:
        print("   " + e)
    print()
    if moved_any == 0:
        print("VERDICT: reader saw NO waypoint change at all -> the key test is")
        print("         inconclusive, not a pass. Investigate before recording.")
    elif moved_notes == 0:
        print("VERDICT: K1CP does move waypoints and the reader sees them, but none")
        print("         of the moved ones are map notes. The 0-moved pass is REAL.")
    else:
        print("VERDICT: %d MAP NOTES moved - k1cp_keytest disagrees and is wrong."
              % moved_notes)


if __name__ == "__main__":
    main(sys.argv[1:])
