"""Freeze the reviewed note-correction table into the shipped patcher's data.

The dev pipeline re-derives every table key from the real module files, so it
needs PyKotor and a full KOTOR install (`note_table_patch.load_corrections`).
The player's patcher must not need either, and must not depend on the player's
own modules: another mod that repositions a note would change the derived key,
and the correction that mod's author never asked for would silently move to
their new position. Freezing the table here makes the shipped bytes exactly the
bytes this project reviewed and confirmed in game; at runtime a key that no
longer matches is simply skipped, which is the designed behaviour anyway.

    python tools/freeze_note_table.py            # (re)generate and verify
    python tools/freeze_note_table.py --check    # verify only; nonzero on drift

`--check` is the gate: it fails if the frozen blob and the CSV+modules have
drifted apart, so the release can never ship a table nobody reviewed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import note_table_patch as ntp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "patcher", "data")
BIN = os.path.join(DATA, "note_table.bin")
META = os.path.join(DATA, "note_table.json")


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def build():
    """(table_bytes, metadata) re-derived from the CSV and the real modules."""
    corrections = ntp.load_corrections()
    table = ntp.build_table(corrections)
    with open(ntp.CORRECTIONS, "rb") as fh:
        csv_sha = sha256(fh.read())
    meta = {
        "entries": len(corrections),
        "entry_bytes": ntp.ENTRY_BYTES,
        "bytes": len(table),
        "sha256": sha256(table),
        "source_csv": os.path.relpath(ntp.CORRECTIONS, ROOT).replace("\\", "/"),
        "source_csv_sha256": csv_sha,
        "modules": sorted({c["module"] for c in corrections}),
        "generated": time.strftime("%Y-%m-%d"),
    }
    return table, meta


def load_frozen():
    """(table_bytes, metadata) as shipped, or (None, None) if not frozen yet."""
    if not (os.path.isfile(BIN) and os.path.isfile(META)):
        return None, None
    with open(BIN, "rb") as fh:
        table = fh.read()
    with open(META, encoding="utf-8") as fh:
        meta = json.load(fh)
    return table, meta


def check():
    frozen, fmeta = load_frozen()
    if frozen is None:
        print("no frozen table at %s" % os.path.relpath(BIN, ROOT))
        return 1
    if sha256(frozen) != fmeta.get("sha256") or len(frozen) != fmeta.get("bytes"):
        print("FAIL: %s does not match its own manifest" % os.path.relpath(BIN, ROOT))
        return 1
    table, meta = build()
    if table != frozen:
        print("FAIL: frozen table differs from the CSV + modules\n"
              "  frozen %d entries, sha256 %s\n"
              "  live   %d entries, sha256 %s\n"
              "Re-run without --check once the change is reviewed."
              % (fmeta["entries"], fmeta["sha256"], meta["entries"], meta["sha256"]))
        return 1
    print("frozen table matches the CSV and the real module files: "
          "%d entries, %d bytes, sha256 %s"
          % (meta["entries"], meta["bytes"], meta["sha256"]))
    return 0


def freeze():
    table, meta = build()
    frozen, _ = load_frozen()
    if frozen == table:
        print("unchanged: %d entries, sha256 %s" % (meta["entries"], meta["sha256"]))
        return 0
    os.makedirs(DATA, exist_ok=True)
    with open(BIN, "wb") as fh:
        fh.write(table)
    with open(META, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")

    with open(BIN, "rb") as fh:                      # verify from disk
        back = fh.read()
    if back != table:
        print("FAIL: readback mismatch on %s" % BIN)
        return 1
    print("wrote %s\n      %s\n%d entries, %d bytes, sha256 %s"
          % (os.path.relpath(BIN, ROOT), os.path.relpath(META, ROOT),
             meta["entries"], meta["bytes"], meta["sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv[1:] else freeze())
