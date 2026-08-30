"""Pull the *Larger Text Fonts* mod out of Override/, or put it back.

Test for the missing item stack-count number (open item 4). The count is drawn by
engine code, not by a GUI control, so the font metrics are the only thing our
install changes about it: `fnt_d16x16b` went fontheight 0.19 -> 0.32 with its
baseline moved 0.15 -> 0.32, i.e. digits 68% taller in a fixed-size badge.

    python tools/font_test.py off     # fonts -> backups/, vanilla fonts take over
    python tools/font_test.py on      # put them back
    python tools/font_test.py status

Treated as ONE group on purpose (project lesson: bisect by group, not file by
file). If the number comes back with all six gone, bisect from there.
"""

import os
import shutil
import sys

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERRIDE = os.path.join(GAME, "Override")
PARKED = os.path.join(PROJ, "backups", "override-fonts-removed-2026-08-28")

STEMS = ["fnt_d16x16b", "dialogfont16x16", "dialogfont16x16b",
         "dialogfont10x10b", "pfont16x16b", "savefont16x16b"]
EXTS = [".tga", ".txi"]


def pairs(root):
    return [(s + e) for s in STEMS for e in EXTS
            if os.path.isfile(os.path.join(root, s + e))]


def cmd_status():
    print("Override :", len(pairs(OVERRIDE)), "font file(s)", sorted(pairs(OVERRIDE)))
    print("parked   :", len(pairs(PARKED)) if os.path.isdir(PARKED) else 0,
          "font file(s) in", PARKED)
    print("Override total files:", len(os.listdir(OVERRIDE)))


def cmd_off():
    live = pairs(OVERRIDE)
    if not live:
        print("nothing to do - no modded fonts in Override")
        return 1
    os.makedirs(PARKED, exist_ok=True)
    for f in live:
        shutil.move(os.path.join(OVERRIDE, f), os.path.join(PARKED, f))
        print("parked", f)
    print("\n%d file(s) moved. The game now uses the vanilla .tpc fonts from "
          "TexturePacks/swpc_tex_gui.erf." % len(live))
    print("CHECK IN GAME: open the inventory on a stacked item (grenades, medpacs)")
    print("  number back  -> the font mod is the cause; bisect which font")
    print("  still absent -> fonts are cleared, the badge rect is engine-side")
    cmd_status()
    return 0


def cmd_on():
    if not os.path.isdir(PARKED):
        print("nothing parked at", PARKED)
        return 1
    back = pairs(PARKED)
    for f in back:
        shutil.move(os.path.join(PARKED, f), os.path.join(OVERRIDE, f))
        print("restored", f)
    if not os.listdir(PARKED):
        os.rmdir(PARKED)
    cmd_status()
    return 0


if __name__ == "__main__":
    cmds = {"off": cmd_off, "on": cmd_on, "status": cmd_status}
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg not in cmds:
        print(__doc__)
        sys.exit(2)
    sys.exit(cmds[arg]() or 0)
