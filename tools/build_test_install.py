"""Build and deploy a full official-chain test install at any k1hrm resolution.

    python tools/build_test_install.py 1600x1200 --letterbox yes
    python tools/build_test_install.py 2560x1600 --letterbox no --home patcher

Dev tool for the resolution testing in RELEASE_PLAN.md Phase 4. NOT shipped:
a player runs UniWS and k1hrm themselves and then patcher/install.py. This does
the same thing to *our* machine, in one command, so a re-test costs a minute
instead of a hand sequence over a 4 MB binary.

The order never leaves the install in a state we cannot name:

  1. build the official chain (UniWS artifact -> official hires_patcher.pl at
     W H <letterbox>) entirely under staging/, touching nothing live;
  2. back up the live exe, the .gui files about to be overwritten and
     swkotor.ini into backups/ - never into the game folder (CLAUDE.md);
  3. write the base exe and swap in k1hrm's own gui.WxH set;
  4. run the shipped patcher/install.py on it, which re-verifies from disk;
  5. point swkotor.ini at W x H;
  6. record what was deployed in staging/testbuild/deployed.json.

If step 4 refuses, the install is left as a plain UniWS + k1hrm build at W x H -
playable, and this command is re-runnable on it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "patcher"))

import backup_paths  # noqa: E402
import qa  # noqa: E402
from k1amf import detect  # noqa: E402
from k1amf.detect import Refusal  # noqa: E402

STAGING = os.path.join(ROOT, "staging", "testbuild")
DEPLOYED = os.path.join(STAGING, "deployed.json")
# One bounded stash of what was there before this tool ever ran. Every later
# live exe is itself a test build this tool can rebuild in one command, so
# re-stashing each time would only accumulate 4 MB copies (the Phase 6 tidy-up).
EXE_STASH_SUFFIX = ".pre-testbuild-backup"
INI_STASH_SUFFIX = ".pre-testbuild-backup"
GUI_STASH = os.path.join(backup_paths.BACKUPS, "override-gui.pre-testbuild")

CHECKLIST = """\
  1. Area Map fills its box, centred
  2. Area Map note markers sit on their rooms
  3. HUD minimap renders (not black)          <- mandatory, broke twice
  4. Player + party markers track while walking
  5. Open and close the Area Map repeatedly - no crash, no corruption"""


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_resolution(text):
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise SystemExit("resolution must look like 1600x1200, not %r" % text)


def find_gui_set(width, height):
    """k1hrm's own .gui set for this resolution, or a listing of what it ships."""
    sets = qa.discover_resolutions()
    for w, h, path in sets:
        if (w, h) == (width, height):
            return path
    have = ", ".join("%dx%d" % (w, h) for w, h, _ in sets)
    raise SystemExit(
        "k1hrm 1.5 ships no gui set for %dx%d, so there is nothing to test "
        "against.\nIt has: %s" % (width, height, have))


def stash_once(target, suffix):
    """Back up `target` into backups/ the first time only.

    A second copy would be a backup of a test build this tool can rebuild, so
    it is not worth 4 MB. Returns the path that holds the original.
    """
    dst = backup_paths.backup_path(target, suffix)
    if os.path.exists(dst):
        print("  already stashed: %s" % dst)
        return dst
    return backup_paths.make_backup(target, suffix)


def stash_gui_once(game_dir, names):
    """Same rule for the Override .gui files this run is about to overwrite."""
    if os.path.isdir(GUI_STASH):
        print("  already stashed: %s" % GUI_STASH)
        return GUI_STASH
    os.makedirs(GUI_STASH)
    kept = 0
    for name in names:
        live = os.path.join(game_dir, "Override", name)
        if os.path.isfile(live):
            shutil.copy2(live, os.path.join(GUI_STASH, name))
            kept += 1
    print("  stashed %d Override .gui file(s) to %s" % (kept, GUI_STASH))
    return GUI_STASH


def swap_gui_set(game_dir, gui_dir):
    """Copy k1hrm's set for this resolution over the live Override files."""
    override = os.path.join(game_dir, "Override")
    if not os.path.isdir(override):
        os.makedirs(override)
    names = sorted(n for n in os.listdir(gui_dir)
                   if os.path.isfile(os.path.join(gui_dir, n)))
    stash_gui_once(game_dir, names)
    for name in names:
        shutil.copy2(os.path.join(gui_dir, name), os.path.join(override, name))
    print("  copied %d file(s) from %s into Override/"
          % (len(names), os.path.relpath(gui_dir, ROOT)))
    return names


# UniWS writes its own undo records into the game folder - swkotore.undo1-4 and
# swkotorc.undom1-2 (RELEASE_PLAN.md section 2.9). They are the prerequisite's,
# by its own design, and deleting them would destroy its undo. So the project's
# "no backups in the game folder" rule is reported here, not enforced: what it
# is really guarding against is *our* backups creeping in.
UNIWS_UNDO = ("swkotore.undo1", "swkotore.undo2", "swkotore.undo3",
              "swkotore.undo4", "swkotorc.undom1", "swkotorc.undom2")


def check_game_folder_clean(game_dir):
    try:
        backup_paths.assert_clean(game_dir)
    except AssertionError as exc:
        stray = [name for name in os.listdir(game_dir)
                 if name.endswith(("-backup", ".undo1", ".undo2", ".undo3",
                                   ".undo4", ".undom1", ".undom2"))
                 and name not in UNIWS_UNDO]
        if stray:
            raise SystemExit("%s\nThese are not UniWS's: %s" % (exc, stray))
        print("  note: UniWS's own undo records are in the game folder "
              "(%d files) - the prerequisite's, left alone" % len(UNIWS_UNDO))


def set_ini_resolution(path, width, height):
    """Rewrite Width/Height under [Graphics Options] only, keeping line ends."""
    with open(path, "r", encoding="latin-1", newline="") as fh:
        lines = fh.read().splitlines(True)

    section = None
    seen = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].lower()
            continue
        if section != "graphics options":
            continue
        for key, value in (("Width", width), ("Height", height)):
            if stripped.lower().startswith(key.lower() + "="):
                seen[key] = stripped.split("=", 1)[1]
                eol = line[len(line.rstrip("\r\n")):]
                lines[i] = "%s=%d%s" % (key, value, eol)

    missing = [k for k in ("Width", "Height") if k not in seen]
    if missing:
        raise SystemExit(
            "no %s under [Graphics Options] in %s - run the game once at any "
            "resolution first, so it writes the key." % (" or ".join(missing), path))

    with open(path, "w", encoding="latin-1", newline="") as fh:
        fh.writelines(lines)
    print("  swkotor.ini [Graphics Options]: %sx%s -> %dx%d"
          % (seen["Width"], seen["Height"], width, height))


def build_base(width, height, letterbox):
    """The official chain up to (not including) our layer, as a file on disk."""
    os.makedirs(qa.WORK, exist_ok=True)
    os.makedirs(STAGING, exist_ok=True)
    if not os.path.isfile(qa.UNIWS_BASE):
        raise SystemExit("no UniWS artifact at %s" % qa.UNIWS_BASE)
    if not os.path.isfile(qa.KHRM_PL):
        raise SystemExit("no official k1hrm at %s" % qa.KHRM_PL)
    try:
        data = qa.build_official_base(width, height, letterbox)
    except FileNotFoundError:
        raise SystemExit(
            "perl is not on PATH. The official hires_patcher.pl is the only "
            "supported way to build the prerequisite (its shipped .exe is the "
            "one with the F25 defect).")
    out = os.path.join(STAGING, "swkotor.exe.base.%dx%d.letterbox-%s"
                       % (width, height, letterbox))
    with open(out, "wb") as fh:
        fh.write(data)
    return out


def run_patcher(exe_path, home):
    env = dict(os.environ)
    if home:
        os.makedirs(home, exist_ok=True)
        env["K1AMF_HOME"] = home
    cmd = [sys.executable, os.path.join(ROOT, "patcher", "install.py"),
           "--exe", exe_path]
    return subprocess.run(cmd, env=env, cwd=ROOT).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("resolution", help="e.g. 1600x1200")
    ap.add_argument("--letterbox", choices=("yes", "no"), default="no",
                    help="k1hrm's dialogue letterbox option (default: no, "
                         "matching the in-game-confirmed exe)")
    ap.add_argument("--game", metavar="DIR", help="the KOTOR folder, if "
                    "auto-detection picks the wrong one")
    ap.add_argument("--home", choices=("staging", "patcher"), default="staging",
                    help="where the patcher writes its backup and manifest. "
                         "staging (default) keeps test builds out of patcher/; "
                         "use patcher for the build you intend to keep playing")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the base exe only; do not touch the install")
    args = ap.parse_args(argv)

    width, height = parse_resolution(args.resolution)
    gui_dir = find_gui_set(width, height)

    print("building the official chain for %dx%d, letterbox %s"
          % (width, height, args.letterbox))
    base = build_base(width, height, args.letterbox)
    print("  base exe: %s" % os.path.relpath(base, ROOT))
    print("  md5 %s, %d bytes" % (md5(base), os.path.getsize(base)))

    if args.dry_run:
        print("\n--dry-run: the install was not touched.")
        return 0

    game_dir = detect.find_game_dir(args.game,
                                    start=os.path.join(ROOT, "patcher"))
    exe_path = os.path.join(game_dir, "swkotor.exe")
    ini_path = os.path.join(game_dir, "swkotor.ini")
    print("\ngame folder: %s" % game_dir)
    print("  live exe md5 %s" % md5(exe_path))

    print("\nbacking up what this run replaces (into backups/, never the game folder)")
    exe_stash = stash_once(exe_path, EXE_STASH_SUFFIX)
    ini_stash = stash_once(ini_path, INI_STASH_SUFFIX)

    print("\ndeploying")
    shutil.copyfile(base, exe_path)
    if md5(exe_path) != md5(base):
        raise SystemExit("the exe did not read back identical after copying; "
                         "restore from %s" % exe_stash)
    print("  wrote the base exe to %s" % exe_path)
    gui_names = swap_gui_set(game_dir, gui_dir)
    check_game_folder_clean(game_dir)

    print("\nrunning the shipped patcher on it")
    rc = run_patcher(exe_path, os.path.join(STAGING, "k1amf-home")
                     if args.home == "staging" else None)
    if rc != 0:
        print("\nthe patcher refused. The install is a plain UniWS + k1hrm "
              "build at %dx%d right now - playable, and this command can be "
              "re-run on it." % (width, height))
        return rc

    print("\npointing the game at this resolution")
    set_ini_resolution(ini_path, width, height)

    record = {
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "resolution": [width, height],
        "letterbox": args.letterbox,
        "game_dir": game_dir,
        "gui_set": os.path.relpath(gui_dir, ROOT),
        "gui_files": len(gui_names),
        "base_exe": os.path.relpath(base, ROOT),
        "base_md5": md5(base),
        "installed_md5": md5(exe_path),
        "patcher_home": args.home,
        "stashed": {"exe": os.path.relpath(exe_stash, ROOT),
                    "ini": os.path.relpath(ini_stash, ROOT),
                    "override_gui": os.path.relpath(GUI_STASH, ROOT)},
    }
    os.makedirs(STAGING, exist_ok=True)
    with open(DEPLOYED, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")

    print("\n" + "=" * 72)
    print("TEST BUILD DEPLOYED: %dx%d, letterbox %s, md5 %s"
          % (width, height, args.letterbox, record["installed_md5"]))
    print("record: %s" % os.path.relpath(DEPLOYED, ROOT))
    print("=" * 72)
    print("\nIn game, the Phase 4 checklist:")
    print(CHECKLIST)
    if args.letterbox == "yes" and width * 3 == height * 4:
        # hires_patcher.pl:181-184 forces letterbox off at exactly 4:3, so a
        # 4:3 build cannot test the letterbox gap however it is answered.
        print("\nNote: k1hrm turns the letterbox patch OFF by itself at 4:3, so "
              "this build\n  is byte-identical to --letterbox no. The letterbox "
              "question needs a\n  non-4:3 resolution.")
    elif args.letterbox == "yes":
        print("  + letterbox: start any dialogue - the bars should be in "
              "proportion\n    and the subtitles inside the picture, not "
              "pushed off the bottom.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refusal as exc:
        print("\n%s" % exc)
        raise SystemExit(1)
