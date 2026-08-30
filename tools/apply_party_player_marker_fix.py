"""
Standalone applier for add_party_player_marker_fix() (see the big comment
above that function in hires_patch.py for the full design/root-cause writeup).

Deliberately separate from hires_patch.py's own patch()/__main__, same reason
as apply_marker_fix.py: this fix is INCREMENTAL, applied on top of an exe that
already has add_area_map_marker_fix() (the notes fix) deployed - it reuses
that fix's kx/ky float constants rather than rewriting them.

Usage: python tools/apply_party_player_marker_fix.py EXE

(No width/height args - unlike apply_marker_fix.py, this doesn't compute new
constants, it only reads the ones already written by the notes fix.)

Backs up EXE first (to EXE + ".pre-partyplayerfix-backup"), applies the fix to
a fresh copy in memory, writes the result back to EXE, then reads it back and
independently re-disassembles both hooks + both caves with capstone so the
bytes actually on disk are verified, not just trusted from the write call.
"""

import shutil

import backup_paths
import sys

import capstone

from hires_patch import (
    add_party_player_marker_fix,
    PARTY_HOOK_VA,
    PARTY_HOOK_JMP,
    PARTY_CAVE_VA,
    PARTY_CAVE_BYTES,
    PLAYER_HOOK_VA,
    PLAYER_HOOK_JMP,
    PLAYER_HOOK_NOP_PAD,
    PLAYER_CAVE_VA,
    PLAYER_CAVE_BYTES,
    IMAGE_BASE,
)


def verify_readback(data):
    """Independent post-write check: re-disassemble what's actually on disk
    (not the in-memory bytes we just wrote) and print it for visual
    confirmation, plus a byte-exact compare against what we intended to write.
    """
    ok = True

    def check(va, expected, label):
        nonlocal ok
        off = va - IMAGE_BASE
        actual = bytes(data[off:off + len(expected)])
        if actual != expected:
            print(f"  MISMATCH at {label}: on-disk {actual.hex()} != intended {expected.hex()}")
            ok = False
        return actual

    party_hook_actual = check(PARTY_HOOK_VA, PARTY_HOOK_JMP, "party hook")
    party_cave_actual = check(PARTY_CAVE_VA, PARTY_CAVE_BYTES, "party cave")
    player_hook_actual = check(PLAYER_HOOK_VA, PLAYER_HOOK_JMP + PLAYER_HOOK_NOP_PAD, "player hook")
    player_cave_actual = check(PLAYER_CAVE_VA, PLAYER_CAVE_BYTES, "player cave")

    print("\n  readback disassembly (hooks + caves, as actually written to disk):")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for label, va, blob in (
        ("party hook", PARTY_HOOK_VA, party_hook_actual),
        ("party cave", PARTY_CAVE_VA, party_cave_actual),
        ("player hook", PLAYER_HOOK_VA, player_hook_actual),
        ("player cave", PLAYER_CAVE_VA, player_cave_actual),
    ):
        print(f"    -- {label} --")
        for insn in md.disasm(blob, va):
            print(f"    0x{insn.address:X}:  {insn.mnemonic} {insn.op_str}")

    return ok


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} EXE")
        return 1
    exe_path = sys.argv[1]

    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    backup_path = backup_paths.make_backup(exe_path, ".pre-partyplayerfix-backup")

    try:
        add_party_player_marker_fix(data)
    except RuntimeError as e:
        print(f"\nERROR: {e}\nNo changes written.")
        return 1

    with open(exe_path, "wb") as f:
        f.write(data)
    print(f"\nwrote patched exe to {exe_path}")

    with open(exe_path, "rb") as f:
        written = f.read()
    if verify_readback(written):
        print("\nreadback verified byte-exact. NOT yet confirmed in-game - "
              "test both the HUD minimap and the in-menu Area Map (player, "
              "party, and note markers) before trusting this.")
        return 0
    else:
        print(f"\nREADBACK MISMATCH - restore from {backup_path} and investigate before testing in-game.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
