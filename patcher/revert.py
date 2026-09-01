"""K1 Area Map Fixes - uninstaller.

    python revert.py [--force]

Restores the exact exe this patcher backed up, after checking that the file it
is about to replace is still the one it produced. If something else has patched
the exe since (another mod, a re-run of k1hrm, a Steam file verification),
restoring would silently throw that away, so it stops and says so; --force
overrides once you have read what it found.

Copyright (C) 2026 the K1 Area Map Fixes authors. GPLv3 or later; see LICENSE.
"""
from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from k1amf import PRODUCT                 # noqa: E402
from k1amf import detect, manifest, ui    # noqa: E402
from k1amf.detect import Refusal          # noqa: E402

try:                                    # belt-and-braces: see k1amf/ui.py
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def main(argv):
    force = "--force" in argv
    print("%s - uninstall" % PRODUCT)
    print("")
    print("Uninstalling...")

    record = manifest.read()
    if record is None:
        raise Refusal(
            "I can't find a record of this mod being installed, so there's\n"
            "nothing to undo.\n"
            "\n"
            "If you have already uninstalled it, that is all this means.\n"
            "\n"
            "If you did install it and it was a different Windows account, or\n"
            "the record has been deleted, put back the backup copy of\n"
            "swkotor.exe yourself - or reinstall the Editable Executable and\n"
            "redo UniWS and the high-res menus mod.\n"
            "\n"
            "(Looking for %s.)" % manifest.MANIFEST)

    exe_path = os.path.join(record["game_dir"], record["exe"])
    backup = os.path.join(manifest.HERE, record["backup"])
    if not os.path.isfile(backup):
        raise Refusal(
            "The backup of your original game file is gone:\n"
            "    %s\n"
            "\n"
            "Without it I can't put your game back. If you kept a copy of\n"
            "swkotor.exe somewhere else, copy it back by hand." % backup)
    if not os.path.isfile(exe_path):
        raise Refusal(
            "Your game file isn't where it was when this mod was installed:\n"
            "    %s\n"
            "\n"
            "Did the game move, or did Steam repair it? There's nothing for\n"
            "me to undo here." % exe_path)

    with open(exe_path, "rb") as fh:
        current = fh.read()
    with open(backup, "rb") as fh:
        original = fh.read()

    if detect.sha256(original) != record["before"]["sha256"]:
        raise Refusal(
            "The backup file has been changed since it was made, so it's no\n"
            "longer the game file you had before.\n"
            "\n"
            "I won't copy it over your game - it could make things worse\n"
            "rather than better.")

    if detect.sha256(current) != record["after"]["sha256"]:
        msg = ("Your swkotor.exe isn't the one this mod created - something\n"
               "changed it afterwards. Another mod, or Steam repairing the\n"
               "game, most likely.\n"
               "\n"
               "If I put the old backup back now, whatever that other thing\n"
               "did gets thrown away.")
        if not force:
            raise Refusal(
                msg + "\n\nIf you're happy to lose it, run:   "
                "Uninstall.bat --force")
        print("-" * ui.WIDTH)
        print("  WARNING")
        print("-" * ui.WIDTH)
        for line in msg.splitlines():
            print(("  " + line).rstrip())
        print("")
        print("--force was given, so restoring anyway.")
        print("")

    shutil.copy2(backup, exe_path)
    with open(exe_path, "rb") as fh:
        if detect.sha256(fh.read()) != record["before"]["sha256"]:
            raise Refusal(
                "I put the backup back, but reading it again didn't give the\n"
                "same file, so I can't promise your game is right.\n"
                "\n"
                "Don't start the game. Copy this file:\n"
                "    %s\n"
                "over this one:\n"
                "    %s\n"
                "by hand, replacing it." % (backup, exe_path))

    os.replace(manifest.MANIFEST, manifest.MANIFEST + ".reverted")
    try:
        # The backup has just done its one job - the bytes it held are
        # verified back on the live exe - so keep it around any longer and
        # every install/uninstall cycle leaves another copy behind forever.
        # Best-effort: a successful uninstall must not fail over cleanup.
        os.remove(backup)
    except OSError:
        pass
    try:
        # Only removes it if truly empty - so this can never eat a backup
        # from a different install left over for some other reason, and
        # never touches installed.json.reverted, which stays on purpose.
        os.rmdir(manifest.BACKUP_DIR)
    except OSError:
        pass
    print("")
    print(ui.banner("UNINSTALL FINISHED SUCCESSFULLY"))
    print("")
    print("Your original game file is back. UniWS and the high-res menus mod")
    print("are untouched - your game still runs at %dx%d, it just doesn't"
          % tuple(record["resolution"]))
    print("have the map fixes any more.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Refusal as exc:
        print("")
        print(ui.banner("UNINSTALL STOPPED"))
        print("")
        for line in str(exc).splitlines():
            print(("  " + line).rstrip())
        print("")
        print("  Your game has not been changed.")
        print("")
        print(ui.rule())
        raise SystemExit(1)
