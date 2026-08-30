"""What was patched, so Revert can undo exactly that and nothing else.

Kept beside the patcher, not in the game folder: the install stays clean, and a
player who deletes the mod folder has not left anything behind in their game.
The backup lives next to it for the same reason.
"""
from __future__ import annotations

import json
import os
import shutil
import time

from . import PRODUCT, __version__
from .detect import Refusal, sha256

# K1AMF_HOME moves the backup and the record elsewhere. selftest.py uses it to
# keep test runs out of the shipped folder; it also lets the patcher work from a
# read-only location.
HERE = os.environ.get("K1AMF_HOME") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(HERE, "installed.json")
BACKUP_DIR = os.path.join(HERE, "backup")


def backup_exe(exe_path):
    """Copy the exe next to the patcher, verified, without ever overwriting an
    older backup of a *different* exe."""
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
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    return MANIFEST


def read():
    if not os.path.isfile(MANIFEST):
        return None
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)
