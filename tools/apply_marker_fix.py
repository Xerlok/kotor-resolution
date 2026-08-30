"""
Standalone applier for add_area_map_marker_fix() (see the big comment above
that function in hires_patch.py for the full design/root-cause writeup).

This is deliberately separate from hires_patch.py's own patch()/__main__ -
that pipeline's match-checks expect a VANILLA exe (offsets still at their
known defaults) and this fix is INCREMENTAL, applied on top of an
already-fully-patched exe. Running patch() again against an already-patched
exe would find 0 matches everywhere and refuse to do anything useful.

Usage: python tools/apply_marker_fix.py EXE WIDTH HEIGHT

Backs up EXE first (to EXE + ".pre-markerfix-attempt3-backup"), applies the
fix to a fresh copy in memory, writes the result back to EXE, then reads it
back and independently re-disassembles the hook + cave with capstone so the
bytes actually on disk are verified, not just trusted from the write call.
"""

import shutil

import backup_paths
import sys

import capstone

from hires_patch import (
    add_area_map_marker_fix,
    MARKER_HOOK_VA,
    MARKER_CAVE_VA,
    MARKER_CAVE_BYTES,
    MARKER_HOOK_JMP,
    IMAGE_BASE,
)


def verify_readback(data):
    """Independent post-write check: re-disassemble what's actually on disk
    (not the in-memory bytes we just wrote) and print it for visual
    confirmation, plus a byte-exact compare against what we intended to write.
    """
    hook_off = MARKER_HOOK_VA - IMAGE_BASE
    cave_off = MARKER_CAVE_VA - IMAGE_BASE

    hook_actual = bytes(data[hook_off:hook_off + len(MARKER_HOOK_JMP)])
    cave_actual = bytes(data[cave_off:cave_off + len(MARKER_CAVE_BYTES)])

    ok = True
    if hook_actual != MARKER_HOOK_JMP:
        print(f"  MISMATCH at hook: on-disk {hook_actual.hex()} != intended {MARKER_HOOK_JMP.hex()}")
        ok = False
    if cave_actual != MARKER_CAVE_BYTES:
        print(f"  MISMATCH at cave: on-disk {cave_actual.hex()} != intended {MARKER_CAVE_BYTES.hex()}")
        ok = False

    print("\n  readback disassembly (hook + cave, as actually written to disk):")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for insn in md.disasm(hook_actual, MARKER_HOOK_VA):
        print(f"    0x{insn.address:X}:  {insn.mnemonic} {insn.op_str}")
    for insn in md.disasm(cave_actual, MARKER_CAVE_VA):
        print(f"    0x{insn.address:X}:  {insn.mnemonic} {insn.op_str}")

    return ok


def main():
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} EXE WIDTH HEIGHT")
        return 1
    exe_path, width, height = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    backup_path = backup_paths.make_backup(exe_path, ".pre-markerfix-attempt3-backup")

    try:
        add_area_map_marker_fix(data, width, height)
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
              "test both the HUD minimap and the in-menu Area Map before "
              "trusting this.")
        return 0
    else:
        print(f"\nREADBACK MISMATCH - restore from {backup_path} and investigate before testing in-game.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
