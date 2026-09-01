"""K1 Area Map Fixes - installer.

    python install.py [GAME_FOLDER] [--details] [--dry-run] [--exe PATH]

Fixes the KOTOR 1 Area Map at high resolutions: the map fills its box, the
player, party and map-note markers land where they belong, and 250 map notes
whose stored positions were wrong are corrected.

REQUIRES, and does not include: UniWS, then KotOR High Resolution Menus
(k1hrm) by ndix UR. Install those first, at the resolution you want to play at.
This patcher reads that resolution out of the exe and refuses to run if either
prerequisite is missing.

Two output levels. The default is written for someone who has never modded
before: what happened, in words, no addresses. `--details` adds the byte-level
running commentary - which offsets were written, what the caves and hooks are,
and the full 21-line verification. Everything `--details` would have printed is
written to last-run-log.txt on every run regardless, so a bug report is a file
to attach rather than a flag to re-run with.

Copyright (C) 2026 the K1 Area Map Fixes authors. GPLv3 or later; see LICENSE.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from k1amf import PRODUCT, __version__            # noqa: E402
from k1amf import detect, manifest, steps, ui, verify  # noqa: E402
from k1amf.detect import Refusal                   # noqa: E402
from k1amf.steps import PatchError                 # noqa: E402

LOG_NAME = "last-run-log.txt"

try:                                    # belt-and-braces: see k1amf/ui.py
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


class Output:
    """Two streams into one transcript.

    `say` is for the player. `detail` is for whoever has to diagnose it later:
    it always reaches the log, and reaches the screen only with --details. The
    log is written even when the run fails, which is exactly when it matters.
    """

    def __init__(self):
        self.details = False
        self.lines = []

    def say(self, msg=""):
        print(msg)
        self.lines.append(msg)

    def detail(self, msg=""):
        if self.details:
            print(msg)
        self.lines.append(msg)

    def block(self, text, how):
        for line in str(text).splitlines():
            how(("  " + line).rstrip())

    def save(self):
        try:
            # Next to Install.bat, not next to the backup: this file exists to
            # be found and attached to a bug report.
            path = os.path.join(manifest.visible_home(), LOG_NAME)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.lines) + "\n")
            return path
        except OSError:
            return None          # a read-only folder must not fail the install


out = Output()


def main(argv):
    out.details = "--details" in argv
    dry_run = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    exe_override = None
    if "--exe" in argv:
        exe_override = argv[argv.index("--exe") + 1]
        args = [a for a in args if a != exe_override]

    out.say("%s %s" % (PRODUCT, __version__))
    out.say("")

    detect.check_not_temp(manifest.visible_home())

    # --- find the game ---------------------------------------------------
    out.say("Checking your game...")
    if exe_override:
        exe_path = os.path.abspath(exe_override)
        game_dir = os.path.dirname(exe_path)
        if not os.path.isfile(exe_path):
            raise Refusal("There is no file here:\n    %s" % exe_path)
    else:
        game_dir = detect.find_game_dir(args[0] if args else None,
                                        start=os.path.dirname(os.path.abspath(__file__)))
        exe_path = os.path.join(game_dir, "swkotor.exe")
    out.say(ui.field("Location", game_dir))

    with open(exe_path, "rb") as fh:
        before = bytearray(fh.read())

    # --- gates -----------------------------------------------------------
    detect.check_build(before, exe_path)
    out.detail("  swkotor.exe is the %d-byte Editable Executable" % len(before))

    width, height = detect.read_resolution(before)
    out.say(ui.field("Resolution", "%dx%d" % (width, height)))
    out.say(ui.field("UniWS", "installed"))
    out.say(ui.field("High-res menus", "installed"))

    centring = detect.check_centring(before, width, height)
    if centring == "stale":
        # Real, and worth having in the log for a bug report, but not
        # something the default player needs to be told mid-install - the
        # patcher is already finishing the job for them.
        out.detail("  the high-res menus mod left the map centring vanilla;")
        out.detail("  finishing that off (sitting %d across, %d down) -"
                   % ((width - detect.VANILLA_W) // 2,
                      (height - detect.VANILLA_H) // 2))
        out.detail("  Uninstall.bat undoes it along with everything else")
    else:
        out.detail("  the map centring values are already correct")

    import hires_patch  # noqa: E402  (tools/ is on sys.path via k1amf)
    icon_s = hires_patch.note_icon_scale(width, height)
    if icon_s > 1:
        out.detail("  map markers will be made %dx bigger for this resolution"
                   % icon_s)
    else:
        out.detail("  map markers stay their vanilla size at this resolution")

    extent = detect.check_map_gui(game_dir, width, height)
    out.say(ui.field("Menu files", "match your resolution"))
    out.detail("  Override/map.gui draws the map at %s" % (extent,))

    conflicts = detect.conflicting_mods(game_dir)
    if conflicts:
        out.say("")
        out.block(conflicts, out.say)
    else:
        out.say(ui.field("Conflicts", "none found"))

    state, per_layer = detect.layer_state(before, width, height)
    if state == "full":
        out.say("")
        out.say(ui.banner("NOTHING TO DO - ALREADY INSTALLED"))
        out.say("")
        out.say("  This mod is already installed. If you want to install it")
        out.say("  again, run Uninstall.bat first.")
        return 0
    if state == "partial":
        for label, st in per_layer.items():
            out.detail("      %-24s %s" % (label, st))
        raise Refusal(
            "A previous install didn't finish.\n"
            "\n"
            "Run Uninstall.bat to put your backup back, then try again. If\n"
            "that doesn't work, restore an unmodified swkotor.exe and redo\n"
            "UniWS and the high-res menus mod.\n"
            "\n"
            "I won't patch on top of a half-finished install - that would\n"
            "break the game for real.")

    table, meta = steps.load_note_table()
    out.detail("  %d map-note corrections, sha256 %s..."
               % (meta["entries"], meta["sha256"][:16]))

    # --- patch, in memory ------------------------------------------------
    # The layers narrate themselves in byte-level terms, which is right for the
    # log and wrong for the screen. Capture it rather than teach every layer
    # about two output levels.
    after = bytearray(before)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        done = steps.apply_all(after, width, height, table)
    out.detail("")
    out.detail("-- what was written ---------------------------------------")
    out.block(buf.getvalue().rstrip("\n"), out.detail)

    if dry_run:
        out.say("")
        out.say("--dry-run: nothing was written to your game.")
        return 0

    out.say("")
    out.say("Backing up your original game file...")
    backup = manifest.backup_exe(exe_path)
    out.say("  Saved to: %s" % backup)
    out.detail("  (safely away from this folder and your game; Uninstall.bat")
    out.detail("  knows where to find it)")

    with open(exe_path, "wb") as fh:
        fh.write(after)
    out.detail("  wrote %s" % exe_path)

    out.say("")
    out.say("Patching...")
    out.say("")
    out.say(ui.done("Map screen fills the available area"))
    out.say(ui.done("Corner minimap still works"))
    out.say(ui.done("Player and party markers land where they belong"))
    out.say(ui.done("Map notes render in the correct position"))
    out.say(ui.done("%d map notes moved to their correct location"
                    % meta["entries"]))
    if icon_s > 1:
        out.say(ui.done("Map markers enlarged %dx for this resolution" % icon_s))

    # --- verify, from disk -----------------------------------------------
    with open(exe_path, "rb") as fh:
        written = bytearray(fh.read())
    if written != after:
        raise PatchError(
            "The file that landed on disk isn't what I wrote, which usually\n"
            "means something else is touching the game folder - antivirus, or\n"
            "a sync tool like OneDrive.\n"
            "\n"
            "Don't start the game. Run Uninstall.bat to put your backup back.")

    import note_table_patch as ntp
    code_va, table_va = ntp.layout(written, len(table))
    results = verify.check(before, written, width, height, table, code_va, table_va)
    out.detail("")
    out.detail("-- checking every change against the file on disk ----------")
    for good, label in results:
        out.detail("  [%s] %s" % ("x" if good else " ", label))

    passed = sum(1 for good, _ in results if good)
    out.say("")
    out.say("Verifying... %d/%d checks passed." % (passed, len(results)))
    if passed != len(results):
        for good, label in results:
            if not good:
                out.say("    FAILED: %s" % label)
        raise PatchError(
            "Something went wrong and I'm not confident the patch is correct.\n"
            "\n"
            "Don't start the game yet. Run Uninstall.bat - it puts your\n"
            "original file back. Nothing is lost.\n"
            "\n"
            "Then please report this, and include the FAILED line above and\n"
            "%s from this folder. That says exactly what happened." % LOG_NAME)

    manifest.write(
        game_dir=game_dir, exe=os.path.basename(exe_path),
        resolution=[width, height], map_gui_extent=list(extent),
        before={"size": len(before), "sha256": detect.sha256(bytes(before))},
        after={"size": len(written), "sha256": detect.sha256(bytes(written))},
        backup=os.path.relpath(backup, manifest.HERE),
        note_table={"entries": meta["entries"], "bytes": meta["bytes"],
                    "sha256": meta["sha256"], "va": hex(table_va)},
        steps=done)

    out.say("")
    out.say(ui.banner("PATCHING FINISHED SUCCESSFULLY"))
    out.say("")
    out.say("You can now launch KOTOR and check:")
    out.say("  - the full-screen map")
    out.say("  - the corner minimap")
    out.say("")
    out.say("If everything looks good, you're done.")
    out.say("")
    out.say("If something is wrong, run Uninstall.bat to restore your")
    out.say("original game file.")
    return 0


if __name__ == "__main__":
    code = 0
    try:
        code = main(sys.argv[1:])
    except (Refusal, PatchError) as exc:
        out.say("")
        out.say(ui.banner("INSTALL STOPPED" if isinstance(exc, Refusal)
                          else "PATCHING FAILED"))
        out.say("")
        out.block(exc, out.say)
        if isinstance(exc, Refusal):
            # Refusals happen before anything is written, by construction.
            out.say("")
            out.say("  Your game has not been changed.")
        out.say("")
        out.say(ui.rule())
        code = 1
    except Exception as exc:                       # noqa: BLE001
        import traceback
        out.detail(traceback.format_exc())
        out.say("")
        out.say(ui.banner("UNEXPECTED ERROR"))
        out.say("")
        out.say("  %s: %s" % (type(exc).__name__, exc))
        out.say("")
        out.say("  Please report this and attach %s from this folder." % LOG_NAME)
        out.say("")
        out.say(ui.rule())
        code = 1
    saved = out.save()
    if saved and not out.details:
        print("\nFull log: %s" % LOG_NAME)
    raise SystemExit(code)
