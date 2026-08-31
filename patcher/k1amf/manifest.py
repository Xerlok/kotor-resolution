"""What was patched, so Revert can undo exactly that and nothing else.

Never in the game folder: the install stays clean, so "what is deployed" is
never ambiguous, and a player who deletes the mod has left nothing behind.

Not in the mod folder either. The record and the backup of the player's
original swkotor.exe go to %LOCALAPPDATA%\\K1AreaMapFixes\\, because the mod
folder is a download: people run Install.bat out of Downloads or out of the zip
itself and then delete it, which used to take their only pre-patch exe with it.
The one thing that stays visible next to Install.bat is last-run-log.txt, which
is there to be attached to a bug report (install.py writes it, see
visible_home()).

Three exceptions, in the order they are checked - see _data_home().
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

from . import PRODUCT, __version__
from .detect import Refusal, sha256


def _release_root(start):
    """The folder holding Install.bat, at or above `start`. None if there isn't one.

    Both shipped layouts sit below it: the frozen build in `Patcher\\`, one level
    down, and the Python source in `More info\\source\\`, two. Walking up finds
    either without either having to know where it is.
    """
    here = os.path.abspath(start)
    for _ in range(4):
        if os.path.isfile(os.path.join(here, "Install.bat")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def visible_home():
    """The folder the player sees - the one they double-clicked in.

    Frozen, `__file__` resolves inside PyInstaller's `_internal` directory, so
    it is useless for this; use the exe's own location and walk up. Running
    from source, start at this package's parent - `patcher/` in the repo,
    `More info\\source\\` in the release.
    """
    if getattr(sys, "frozen", False):
        start = os.path.dirname(os.path.abspath(sys.executable))
    else:
        start = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _release_root(start) or start


def _data_home():
    """Where the backup and installed.json live.

    1. K1AMF_HOME wins outright. selftest.py and tools/build_test_install.py
       use it to keep test runs out of the shipped folder, and it lets the
       patcher work from a read-only location.
    2. A development checkout keeps them in `patcher/`, where tools/state.py
       and docs/CURRENT_STATE.md expect them. selftest.py is never shipped
       (build_release.copy_source), so its presence is what marks the repo.
    3. An install made by an earlier build kept them in the release folder;
       if such a record is sitting there, keep using it so Uninstall.bat still
       finds the backup it was told about.

    Otherwise: %LOCALAPPDATA%\\K1AreaMapFixes\\, which survives deleting the
    download. The fallback for a machine with no LOCALAPPDATA (this code runs
    on non-Windows during development) is the usual per-user data directory.
    """
    override = os.environ.get("K1AMF_HOME")
    if override:
        return override
    seen = visible_home()
    if os.path.isfile(os.path.join(seen, "selftest.py")):
        return seen
    if os.path.isfile(os.path.join(seen, "installed.json")):
        return seen
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "K1AreaMapFixes")


HERE = _data_home()
MANIFEST = os.path.join(HERE, "installed.json")
BACKUP_DIR = os.path.join(HERE, "backup")


def backup_exe(exe_path):
    """Copy the exe into HERE, verified, without ever overwriting an older
    backup of a *different* exe."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, "swkotor.exe.original")
    with open(exe_path, "rb") as fh:
        want = sha256(fh.read())
    if os.path.exists(dst):
        with open(dst, "rb") as fh:
            if sha256(fh.read()) != want:
                dst = "%s.%s" % (dst, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(exe_path, dst)
    with open(dst, "rb") as fh:
        if sha256(fh.read()) != want:
            raise Refusal("the backup copy did not read back identical - check "
                          "the disk has free space, and do not run the game "
                          "until this succeeds.")
    return dst


def write(**fields):
    record = {"product": PRODUCT, "patcher_version": __version__,
              "applied": time.strftime("%Y-%m-%dT%H:%M:%S")}
    record.update(fields)
    os.makedirs(HERE, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    return MANIFEST


def read():
    if not os.path.isfile(MANIFEST):
        return None
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)
