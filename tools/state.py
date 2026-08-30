"""What is currently applied, and is it consistent? Read this before anything.

Written so a new session can orient in ONE command instead of re-deriving which
exe is patched, which caves are present and whether the data on disk matches the
binary. Everything here is read from disk - nothing is taken on trust from the
notes, which can lag reality if a session ends abruptly.

    python tools/state.py            # live game exe
    python tools/state.py <exe>      # any other build
"""

from __future__ import annotations

import csv
import glob
import os
import struct
import sys

IMAGE_BASE = 0x400000
LIVE_EXE = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor\swkotor.exe"
GAME_DIR = os.path.dirname(LIVE_EXE)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# note-table patch (this project, 2026-08-28)
NOTE_HOOK_VA = 0x6946EF
NOTE_HOOK_ORIG = bytes.fromhex("894a088bc8")
NOTE_CODE_VA = 0x73C270
NOTE_TABLE_VA = 0x73C2F0
FREE_END_VA = 0x73D000


def _table_bounds(data, code_va):
    """(table_va, table_end_va) read out of the match routine's own immediates.

    The routine loads the table base with `mov ebx, imm32` (B8+r, opcode BB)
    and bounds the scan with `cmp ebx, imm32` (81 FB). Reading them back is how
    we learn where the table actually is, wherever the patcher decided to put it.
    """
    window = bytes(data[code_va - IMAGE_BASE:code_va - IMAGE_BASE + 64])
    base = end = None
    i = 0
    while i < len(window) - 5:
        if window[i] == 0xBB and base is None:
            base = struct.unpack("<I", window[i + 1:i + 5])[0]
            i += 5
            continue
        if window[i] == 0x81 and window[i + 1] == 0xFB and end is None:
            end = struct.unpack("<I", window[i + 2:i + 6])[0]
            i += 6
            continue
        i += 1
    return base, end


def _at(data, va, n):
    off = va - IMAGE_BASE
    return bytes(data[off:off + n])


def describe_exe(path):
    from hires_patch import (MARKER_CAVE_VA, MARKER_CAVE_BYTES, MARKER_HOOK_VA,
                             MARKER_HOOK_JMP, PARTY_CAVE_VA, PARTY_CAVE_BYTES,
                             PLAYER_CAVE_VA, PLAYER_CAVE_BYTES)
    if not os.path.exists(path):
        print("  MISSING: %s" % path)
        return None
    with open(path, "rb") as fh:
        data = fh.read()
    print("  %s" % path)
    print("    size %d bytes" % len(data))

    checks = [
        ("area-map marker calibration cave", MARKER_CAVE_VA, MARKER_CAVE_BYTES),
        ("party marker cave", PARTY_CAVE_VA, PARTY_CAVE_BYTES),
        ("player marker cave", PLAYER_CAVE_VA, PLAYER_CAVE_BYTES),
    ]
    for label, va, want in checks:
        print("    [%s] %s (0x%X)"
              % ("x" if _at(data, va, len(want)) == want else " ", label, va))
    print("    [%s] marker hook 0x%X -> cave"
          % ("x" if _at(data, MARKER_HOOK_VA, 5) == MARKER_HOOK_JMP else " ",
             MARKER_HOOK_VA))

    hooked = _at(data, NOTE_HOOK_VA, 1) == b"\xe9"
    vanilla = _at(data, NOTE_HOOK_VA, 5) == NOTE_HOOK_ORIG
    print("    [%s] NOTE TABLE hook 0x%X%s"
          % ("x" if hooked else " ", NOTE_HOOK_VA,
             "" if (hooked or vanilla) else "  <== neither hooked nor original!"))
    if hooked:
        target = IMAGE_BASE + 0  # decode the rel32
        rel = struct.unpack("<i", _at(data, NOTE_HOOK_VA + 1, 4))[0]
        target = NOTE_HOOK_VA + 5 + rel
        print("        jumps to 0x%X %s" % (target,
              "(expected 0x%X)" % NOTE_CODE_VA if target != NOTE_CODE_VA else ""))
        # Read the table's address out of the match routine rather than assuming
        # it: since 2026-08-29 a table too big for the .text cave lives in the
        # region pe_space.py reserves at the end of .rsrc, so a fixed VA here
        # reported "0 entries" against a perfectly good patch.
        table_va, table_end_va = _table_bounds(data, target)
        if table_va is None:
            print("        cannot find the table address in the match routine "
                  "at 0x%X <== unexpected" % target)
            return 0
        import pe_space
        off = pe_space.rva_to_off(data, table_va - IMAGE_BASE)
        entries = 0
        while True:
            raw = data[off + entries * 16: off + (entries + 1) * 16]
            if len(raw) < 16 or raw == b"\x00" * 16:
                break
            entries += 1
        where = "cave" if table_va < FREE_END_VA else "reserved region (.rsrc)"
        limit = FREE_END_VA if table_va < FREE_END_VA else table_end_va
        print("        table at 0x%X in the %s: %d entries (%d bytes), ends 0x%X"
              % (table_va, where, entries, entries * 16, table_va + entries * 16))
        if entries * 16 != table_end_va - table_va:
            print("        WARNING: routine scans 0x%X..0x%X (%d entries) but "
                  "%d are populated" % (table_va, table_end_va,
                                        (table_end_va - table_va) // 16, entries))
        return entries
    return 0


def main(argv):
    sys.path.insert(0, os.path.join(_ROOT, "tools"))
    target = argv[0] if argv else LIVE_EXE

    print("=" * 72)
    print("BINARY")
    entries = describe_exe(target)

    print()
    print("backups next to it:")
    for p in sorted(glob.glob(target + ".*")):
        print("    %s (%d bytes)" % (os.path.basename(p), os.path.getsize(p)))

    print()
    print("=" * 72)
    print("DATA")
    corr = os.path.join(_ROOT, "output", "note_corrections.csv")
    dec = os.path.join(_ROOT, "output", "note_decisions.csv")
    rows = []
    if os.path.exists(corr):
        with open(corr, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_rule = {}
        for r in rows:
            by_rule[r["rule"]] = by_rule.get(r["rule"], 0) + 1
        print("  note_corrections.csv: %d corrections (%s)"
              % (len(rows), ", ".join("%s=%d" % kv for kv in sorted(by_rule.items()))))
    else:
        print("  note_corrections.csv: MISSING - run note_corrections.py finalize")
    if os.path.exists(dec):
        with open(dec, newline="", encoding="utf-8") as fh:
            d = list(csv.DictReader(fh))
        print("  note_decisions.csv:   %d reviewer decisions" % len(d))
    else:
        print("  note_decisions.csv:   MISSING - the review would be lost")

    if rows and entries is not None:
        agree = (entries == len(rows))
        print("  %s binary has %d entries, CSV has %d"
              % ("OK:" if agree else "MISMATCH:", entries, len(rows)))
        if not agree:
            print("      -> the applied table is NOT the current CSV. Re-apply with:")
            print("         copy <exe>.pre-notetable-backup <exe>   (then note_table_patch.py apply)")

    print()
    print("=" * 72)
    print("GAME DATA (must stay clean - we deliver via the exe, not data edits)")
    stray = sorted(glob.glob(os.path.join(GAME_DIR, "Override", "*.git")))
    stray += sorted(glob.glob(os.path.join(GAME_DIR, "Override", "*.are")))
    stray += sorted(glob.glob(os.path.join(GAME_DIR, "modules", "*.mod")))
    if stray:
        print("  STRAY module data present (Phase 1a test leftovers?):")
        for p in stray:
            print("    %s" % p)
    else:
        print("  Override has no .git/.are and modules/ has no .mod - clean")

    print()
    print("=" * 72)
    print("NEXT: read STATE.md, then docs/CURRENT_STATE.md and docs/FUTURE_WORK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
