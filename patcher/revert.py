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
from k1amf import detect, manifest        # noqa: E402
from k1amf.detect import Refusal          # noqa: E402


def main(argv):
    force = "--force" in argv
    print("%s - revert" % PRODUCT)

    record = manifest.read()
    if record is None:
        raise Refusal(
            "no record of an install (%s is missing), so there is nothing to "
            "revert.\nIf you moved or re-downloaded the patcher folder, use the "
            "backup you kept instead." % os.path.basename(manifest.MANIFEST))

    exe_path = os.path.join(record["game_dir"], record["exe"])
    backup = os.path.join(manifest.HERE, record["backup"])
    if not os.path.isfile(backup):
        raise Refusal("the backup this install recorded is gone:\n    %s" % backup)
    if not os.path.isfile(exe_path):
        raise Refusal("the exe this install recorded is gone:\n    %s" % exe_path)

    with open(exe_path, "rb") as fh:
        current = fh.read()
    with open(backup, "rb") as fh:
        original = fh.read()

    if detect.sha256(original) != record["before"]["sha256"]:
        raise Refusal("the backup file has changed since it was made - it is no "
                      "longer the exe you had before. Refusing to restore it.")

    if detect.sha256(current) != record["after"]["sha256"]:
        msg = ("%s is not the file this patcher wrote - something has changed it "
               "since (another mod, k1hrm re-run, or Steam's file verification).\n"
               "Restoring the backup would throw those changes away."
               % record["exe"])
        if not force:
            raise Refusal(msg + "\nRun  Revert.bat --force  if that is what you want.")
        print("\nWARNING: " + msg + "\n--force given; restoring anyway.")

    shutil.copy2(backup, exe_path)
    with open(exe_path, "rb") as fh:
        if detect.sha256(fh.read()) != record["before"]["sha256"]:
            raise Refusal("the restore did not read back identical. Copy\n    %s\n"
                          "over\n    %s\nby hand before running the game."
                          % (backup, exe_path))

    print("restored %s (%dx%d, as it was before this mod)"
          % (exe_path, *record["resolution"]))
    os.replace(manifest.MANIFEST, manifest.MANIFEST + ".reverted")
    print("UniWS and KotOR High Resolution Menus are still installed; only this "
          "mod's changes were undone.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Refusal as exc:
        print("\n" + "!" * 72)
        print(exc)
        print("\nYour game has not been changed.")
        print("!" * 72)
        raise SystemExit(1)
