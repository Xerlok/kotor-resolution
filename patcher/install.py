"""K1 Area Map Fixes - installer.

    python install.py [GAME_FOLDER] [--dry-run] [--exe PATH]

Fixes the KOTOR 1 Area Map at high resolutions: the map fills its box, the
player, party and map-note markers land where they belong, and 250 map notes
whose stored positions were wrong are corrected.

REQUIRES, and does not include: UniWS, then KotOR High Resolution Menus
(k1hrm) by ndix UR. Install those first, at the resolution you want to play at.
This patcher reads that resolution out of the exe and refuses to run if either
prerequisite is missing.

Copyright (C) 2026 the K1 Area Map Fixes authors. GPLv3 or later; see LICENSE.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from k1amf import PRODUCT, __version__            # noqa: E402
from k1amf import detect, manifest, steps, verify  # noqa: E402
from k1amf.detect import Refusal                   # noqa: E402
from k1amf.steps import PatchError                 # noqa: E402


def rule(title=""):
    print("\n-- %s %s" % (title, "-" * max(0, 68 - len(title))))


def main(argv):
    dry_run = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    exe_override = None
    if "--exe" in argv:
        exe_override = argv[argv.index("--exe") + 1]
        args = [a for a in args if a != exe_override]

    print("%s %s" % (PRODUCT, __version__))
    print("requires UniWS + KotOR High Resolution Menus (k1hrm), already installed")

    # --- find the game ---------------------------------------------------
    if exe_override:
        exe_path = os.path.abspath(exe_override)
        game_dir = os.path.dirname(exe_path)
        if not os.path.isfile(exe_path):
            raise Refusal("no such file: %s" % exe_path)
    else:
        game_dir = detect.find_game_dir(args[0] if args else None,
                                        start=os.path.dirname(os.path.abspath(__file__)))
        exe_path = os.path.join(game_dir, "swkotor.exe")
    print("game folder: %s" % game_dir)

    with open(exe_path, "rb") as fh:
        before = bytearray(fh.read())

    # --- gates -----------------------------------------------------------
    rule("checks")
    detect.check_build(before, exe_path)
    print("  [x] %s is the %d-byte Editable Executable"
          % (os.path.basename(exe_path), len(before)))

    width, height = detect.read_resolution(before)
    print("  [x] k1hrm patched this exe for %dx%d (read from the exe, not asked)"
          % (width, height))

    extent = detect.check_map_gui(game_dir, width, height)
    print("  [x] Override/map.gui draws the map at %s - the .gui set matches "
          "the exe" % (extent,))

    state, per_layer = detect.layer_state(before, width, height)
    if state == "full":
        print("\n%s is already installed on this exe. Nothing to do." % PRODUCT)
        print("To reinstall, run Revert.bat first.")
        return 0
    if state == "partial":
        print("\n  some of this mod is already applied and some is not:")
        for label, st in per_layer.items():
            print("      %-24s %s" % (label, st))
        raise Refusal(
            "a previous run was interrupted, or something else has edited "
            "these bytes.\n"
            "Run Revert.bat, or restore a clean exe (UniWS + k1hrm from a stock "
            "Editable Executable), and run this patcher again. Patching on top "
            "of a half-applied exe would corrupt it.")
    print("  [x] none of this mod is applied yet")

    table, meta = steps.load_note_table()
    print("  [x] %d reviewed map-note corrections, sha256 %s..."
          % (meta["entries"], meta["sha256"][:16]))

    # --- patch, in memory ------------------------------------------------
    rule("patching")
    after = bytearray(before)
    done = steps.apply_all(after, width, height, table)
    for s in done:
        print("  applied: %s" % s["step"])

    if dry_run:
        print("\n--dry-run: nothing was written to disk.")
        return 0

    backup = manifest.backup_exe(exe_path)
    print("\n  backed up your exe to %s" % backup)

    with open(exe_path, "wb") as fh:
        fh.write(after)
    print("  wrote %s" % exe_path)

    # --- verify, from disk -----------------------------------------------
    rule("verifying what is actually on disk")
    with open(exe_path, "rb") as fh:
        written = bytearray(fh.read())
    if written != after:
        raise PatchError(
            "the file on disk is not what we wrote. Restore from\n    %s\n"
            "and do not run the game until it is back." % backup)

    import note_table_patch as ntp
    code_va, table_va = ntp.layout(written, len(table))
    results = verify.check(before, written, width, height, table, code_va, table_va)
    for good, label in results:
        print("  [%s] %s" % ("x" if good else " ", label))
    if not all(good for good, _ in results):
        raise PatchError(
            "verification failed. Your original exe is at\n    %s\n"
            "Restore it before running the game, and please report the failing "
            "line above." % backup)

    path = manifest.write(
        game_dir=game_dir, exe=os.path.basename(exe_path),
        resolution=[width, height], map_gui_extent=list(extent),
        before={"size": len(before), "sha256": detect.sha256(bytes(before))},
        after={"size": len(written), "sha256": detect.sha256(bytes(written))},
        backup=os.path.relpath(backup, manifest.HERE),
        note_table={"entries": meta["entries"], "bytes": meta["bytes"],
                    "sha256": meta["sha256"], "va": hex(table_va)},
        steps=done)

    rule("done")
    print("%s is installed for %dx%d." % (PRODUCT, width, height))
    print("Undo it any time with Revert.bat.")
    print("Record of what was changed: %s" % path)
    print("\nNot yet checked by anyone but this patcher: load a save and look at "
          "BOTH the Area Map (the map screen) and the HUD minimap before a long "
          "session.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (Refusal, PatchError) as exc:
        print("\n" + "!" * 72)
        print(exc)
        if isinstance(exc, Refusal):
            # Refusals happen before anything is written, by construction.
            print("\nYour game has not been changed.")
        print("!" * 72)
        raise SystemExit(1)
