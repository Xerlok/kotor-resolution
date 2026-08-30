"""
Our own reimplementation of UniWS's KOTOR "interface" resolution-gate patch,
ported from its plaintext `patches.ini` (not the compiled uniws.exe) so we
understand and control every byte we write, same philosophy as
`hires_patch.py`.

Background: UniWS's KOTOR patch isn't just "accept a custom resolution" —
you pick one of five hardcoded "interface" presets (800x600 / 1024x768 /
1280x960 / 1280x1024 / 1600x1200), and the patch disables the engine's
internal checks for the *other* three-ish presets so it settles on your
choice as its interface layout reference. All five presets are 4:3 or 5:4
— none match a 16:10 target like 2560x1600 exactly. We originally patched
with "1600x1200 interface"; this tool lets us re-patch a fresh copy with
"1024x768 interface" instead (the choice multiple community guides actually
recommend), to test whether the interface/canvas mismatch is related to the
list-click bug.

Every signature is decoded straight from patches.ini's [hex sig] +
[wildcard flags, one char per byte, '1' = don't-care] format. Byte widths
for each write (imm32 vs imm16) were inferred by decoding the literal
(non-wildcard) bytes as x86 `CMP EAX, imm32` / immediate-value instructions
and cross-checking against the already-known-correct values our first,
GUI-tool-driven UniWS pass produced (800, 600, 1024, 1280, 1600, 640, 480 —
see NOTES.md). Every offset is verified against its expected default value
before writing; refuses to patch on any mismatch rather than guessing.
"""

import shutil

import backup_paths
import struct
import sys


def find_sig(data, sig_hex, wild_str, occur=1):
    """Find the `occur`-th (1-indexed) match of a wildcarded byte signature."""
    sig = bytes.fromhex(sig_hex)
    assert len(sig) == len(wild_str), f"sig/wildcard length mismatch: {len(sig)} vs {len(wild_str)}"
    n = len(sig)
    found = 0
    for pos in range(len(data) - n + 1):
        ok = True
        for i in range(n):
            if wild_str[i] == "0" and data[pos + i] != sig[i]:
                ok = False
                break
        if ok:
            found += 1
            if found == occur:
                return pos
    return None


def read_u32(data, pos):
    return struct.unpack_from("<I", data, pos)[0]


def read_u16(data, pos):
    return struct.unpack_from("<H", data, pos)[0]


def write_u32(buf, pos, value):
    struct.pack_into("<I", buf, pos, value)


def write_u16(buf, pos, value):
    struct.pack_into("<H", buf, pos, value)


# The primary resolution-gate patch: identical regardless of which
# "interface" preset is chosen. sig decodes to a literal `cmp eax, 800`
# (imm32) ... 6 wildcard bytes ... literal `, 600` (imm32).
GATE_SIG = "3D20030000EFEFEFEFEFEF58020000"
GATE_WILD = "000001111110000"
GATE_WIDTH_OFF = 1   # imm32, default 800
GATE_HEIGHT_OFF = 11  # imm32, default 600

# The three-way "which bucket" signature: one literal `cmp eax,1024` ...
# 9 wildcard bytes ... literal `cmp eax,1280` ... 2 wildcard bytes ...
# literal `cmp eax,1600`. All three appear inside ONE match; each named
# sub-patch just points `xoffset` at a different embedded imm32.
BUCKET_SIG = "3D00040000B329EFEFEFEFEFEFEFEFEF3D00050000EFEF3D40060000"
BUCKET_WILD = "0000000111111111000001100000"
BUCKET_1024_OFF = 1
BUCKET_1280_OFF = 17
BUCKET_1600_OFF = 24

# "Movies edit" patches: interface-independent (same for every preset),
# already correctly applied by our first UniWS pass — included here too so
# a from-scratch re-patch reproduces the exact same complete result.
MOVIES1_SIG = "800200007515813DD8D17800E001"
MOVIES1_WILD = "00000000000000"
MOVIES1_WIDTH_OFF = 0   # imm32, default 640
MOVIES1_HEIGHT_OFF = 12  # imm16, default 480

MOVIES2_SIG = "80020000C7442410E001"
MOVIES2_WILD = "0000000000"
MOVIES2_WIDTH_OFF = 0    # imm32, default 640
MOVIES2_HEIGHT_OFF = 8   # imm16, default 480


def patch_interface_1024x768(exe_path, width, height, backup_suffix=".uniws-backup"):
    with open(exe_path, "rb") as f:
        data = f.read()
    buf = bytearray(data)

    # --- locate + verify everything against pristine defaults first ---
    gate_pos = find_sig(data, GATE_SIG, GATE_WILD, occur=1)
    assert gate_pos is not None, "gate signature not found"
    assert read_u32(data, gate_pos + GATE_WIDTH_OFF) == 800, "gate width default mismatch"
    assert read_u32(data, gate_pos + GATE_HEIGHT_OFF) == 600, "gate height default mismatch"

    bucket_pos = find_sig(data, BUCKET_SIG, BUCKET_WILD, occur=1)
    assert bucket_pos is not None, "bucket signature not found"
    assert read_u32(data, bucket_pos + BUCKET_1024_OFF) == 1024, "1024 bucket default mismatch"
    assert read_u32(data, bucket_pos + BUCKET_1280_OFF) == 1280, "1280 bucket default mismatch"
    assert read_u32(data, bucket_pos + BUCKET_1600_OFF) == 1600, "1600 bucket default mismatch"

    m1_pos = find_sig(data, MOVIES1_SIG, MOVIES1_WILD, occur=1)
    assert m1_pos is not None, "movies-edit-1 signature not found"
    assert read_u32(data, m1_pos + MOVIES1_WIDTH_OFF) == 640, "movies1 width default mismatch"
    assert read_u16(data, m1_pos + MOVIES1_HEIGHT_OFF) == 480, "movies1 height default mismatch"

    m2_pos = find_sig(data, MOVIES2_SIG, MOVIES2_WILD, occur=1)
    assert m2_pos is not None, "movies-edit-2 signature not found"
    assert read_u32(data, m2_pos + MOVIES2_WIDTH_OFF) == 640, "movies2 width default mismatch"
    assert read_u16(data, m2_pos + MOVIES2_HEIGHT_OFF) == 480, "movies2 height default mismatch"

    print("All 5 signature locations found and verified against pristine defaults:")
    print(f"  gate patch      @ 0x{gate_pos:X}  (800 -> {width}, 600 -> {height})")
    print(f"  bucket-select   @ 0x{bucket_pos:X}")
    print(f"    1024 (chosen interface -> {width})  @ +0x{BUCKET_1024_OFF:X}")
    print(f"    1280 (disable -> 0)          @ +0x{BUCKET_1280_OFF:X}")
    print(f"    1600 (disable -> 0)          @ +0x{BUCKET_1600_OFF:X}")
    print(f"  movies-edit-1   @ 0x{m1_pos:X}  (640 -> {width}, 480 -> {height})")
    print(f"  movies-edit-2   @ 0x{m2_pos:X}  (640 -> {width}, 480 -> {height})")

    # --- backup, then write ---
    backup_path = backup_paths.make_backup(exe_path, backup_suffix)

    write_u32(buf, gate_pos + GATE_WIDTH_OFF, width)
    write_u32(buf, gate_pos + GATE_HEIGHT_OFF, height)

    # 1024 bucket: this is our chosen interface. Cross-checked against the
    # already-deployed 1600x1200-interface exe from our first (GUI-tool)
    # UniWS pass: its *kept* bucket (1600) was NOT left at the literal 1600 —
    # it was rewritten to the real target width (2560). So "no setx" in
    # patches.ini for the chosen bucket means "use the real width", not
    # "leave untouched" (undocumented uniws.exe behavior, only found by
    # comparing our re-implementation's raw output against the known-good
    # exe before deploying anything — see NOTES.md). Match that here.
    write_u32(buf, bucket_pos + BUCKET_1024_OFF, width)
    write_u32(buf, bucket_pos + BUCKET_1280_OFF, 0)
    write_u32(buf, bucket_pos + BUCKET_1600_OFF, 0)

    write_u32(buf, m1_pos + MOVIES1_WIDTH_OFF, width)
    write_u16(buf, m1_pos + MOVIES1_HEIGHT_OFF, height)
    write_u32(buf, m2_pos + MOVIES2_WIDTH_OFF, width)
    write_u16(buf, m2_pos + MOVIES2_HEIGHT_OFF, height)

    with open(exe_path, "wb") as f:
        f.write(buf)

    # --- read back and confirm ---
    with open(exe_path, "rb") as f:
        check = f.read()
    assert read_u32(check, gate_pos + GATE_WIDTH_OFF) == width
    assert read_u32(check, gate_pos + GATE_HEIGHT_OFF) == height
    assert read_u32(check, bucket_pos + BUCKET_1024_OFF) == width
    assert read_u32(check, bucket_pos + BUCKET_1280_OFF) == 0
    assert read_u32(check, bucket_pos + BUCKET_1600_OFF) == 0
    assert read_u32(check, m1_pos + MOVIES1_WIDTH_OFF) == width
    assert read_u16(check, m1_pos + MOVIES1_HEIGHT_OFF) == height
    assert read_u32(check, m2_pos + MOVIES2_WIDTH_OFF) == width
    assert read_u16(check, m2_pos + MOVIES2_HEIGHT_OFF) == height
    print("Patch successful, all writes confirmed by read-back.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} WIDTH HEIGHT EXE")
        sys.exit(1)
    w, h, exe = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    patch_interface_1024x768(exe, w, h)
