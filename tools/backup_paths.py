"""One place that decides where a patcher's backup goes.

Project rule: **no backup file ever lands inside the game folder.** Every backup
goes to `<project>/backups/`, so the install stays clean enough that "what is
actually deployed" is never ambiguous, and so `Override/`-style folder listings
are not polluted by 4 MB exe copies.

Use `make_backup(target, suffix)` instead of `shutil.copy(target, target + suffix)`.
It also refuses to silently destroy an existing backup: if the name is taken and
the content differs, the new one gets a timestamp instead of overwriting the old
"last known good".
"""

import hashlib
import os
import shutil
import time

BACKUPS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "backups")


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_path(target, suffix):
    """Where the backup of `target` with `suffix` belongs. Never next to target."""
    return os.path.join(BACKUPS, os.path.basename(target) + suffix)


def make_backup(target, suffix, verify=True):
    """Copy `target` into backups/ and return the path actually written.

    - identical backup already there  -> reuse it, copy nothing
    - different backup already there  -> write `<name><suffix>.<timestamp>`
    - verify=True                     -> md5-compare the copy before returning
    """
    os.makedirs(BACKUPS, exist_ok=True)
    dst = backup_path(target, suffix)

    if os.path.exists(dst):
        if _md5(dst) == _md5(target):
            print("backup already present and identical: %s" % dst)
            return dst
        dst = "%s.%s" % (dst, time.strftime("%Y%m%d-%H%M%S"))
        print("NOTE: a different backup already holds that name, so this one is %s"
              % os.path.basename(dst))

    shutil.copy2(target, dst)
    if verify and _md5(dst) != _md5(target):
        raise IOError("backup readback mismatch: %s" % dst)
    print("backed up to %s%s" % (dst, " (verified)" if verify else ""))
    return dst


def assert_clean(game_dir):
    """Fail loudly if backup artefacts have crept into the game folder."""
    bad = [f for f in os.listdir(game_dir)
           if f.endswith(("-backup", ".undo1", ".undo2", ".undo3", ".undo4",
                          ".undom1", ".undom2"))
           or ".exe." in f.lower()]
    if bad:
        raise AssertionError(
            "backup files found in the game folder (project rule says backups live "
            "in backups/ only): %s" % bad)
