"""Phase 3: the exe-side map-note correction table.

Injects a lookup table plus a small match routine into the Area Map's own
note-draw path, so corrected note positions come from code instead of from
edited game data. Chosen over a `.git` data edit because the Phase 1a test
showed a data edit reaches an existing save only by discarding that module's
cached state (map exploration reset; one crash) - see `PHASE1A-TEST.md`.

WHERE IT HOOKS
--------------
Function 0x6943D0 (the Area Map's own draw), where a note's world position is
copied into the argument block for the transform at 0x578E00:

    0x6946DD  mov ecx,[esi]        ; note world X   (esi = note position)
    0x6946E4  mov [edx],ecx        ; -> argument block
    0x6946E6  mov ecx,[esi+4]      ; note world Y
    0x6946E9  mov [edx+4],ecx
    0x6946EC  mov ecx,[esi+8]      ; note world Z
    0x6946EF  mov [edx+8],ecx      | exactly 5 bytes - the hook window
    0x6946F2  mov ecx,eax          |
    0x6946F4  call 0x578e00        ; resume here

The correction is applied to the **stack copy** at [edx]/[edx+4], so the note's
own data in memory is never touched. This is a separate 5-byte hook, which
leaves the three existing verified caves (0x73C1D0 notes-calibration, 0x73C20C
party, 0x73C232 player) completely untouched.

Only this one call site is patched. The player/party markers do not pass through
here at all - they read a cached position via 0x5791B0 - and neither does the
generic HUD/minimap path, so by construction this cannot move them.

WHY A POSITION KEY IS SAFE
--------------------------
All 340 map notes in the game have distinct (XPosition, YPosition) float32
pairs, so keying on position cannot move the wrong note. Verified by
`note_corrections.py` on every build, and re-verified here against the real
module files rather than against the CSV's decimal text.

If another mod repositions a note, its key stops matching and that note is
simply left alone - their fix wins, and nothing is corrupted.

    python tools/note_table_patch.py plan  [EXE]      # dry run, no writes
    python tools/note_table_patch.py apply <EXE>      # patch, then verify readback
"""

from __future__ import annotations

import os
import shutil

import backup_paths
import struct
import sys

import capstone

import pe_space

IMAGE_BASE = 0x400000

HOOK_VA = 0x6946EF
HOOK_DEFAULT = bytes.fromhex("894a088bc8")   # mov [edx+8],ecx ; mov ecx,eax
RESUME_VA = 0x6946F4                          # call 0x578e00, unchanged

# The free zero tail of .text, after the three existing caves (last one ends at
# 0x73C263). Verified all-zero in the patched exe before anything is written.
CAVE_VA = 0x73C270
FREE_END_VA = 0x73D000

ENTRY_BYTES = 16

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORRECTIONS = os.path.join(_ROOT, "output", "note_corrections.csv")


def f32(v):
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def f32_bytes(v):
    return struct.pack("<f", float(v))


# --------------------------------------------------------------------------
def load_corrections(path=CORRECTIONS, game=None):
    """Corrections from the reviewed CSV, with every key re-derived from the
    real module files.

    The CSV writes positions as %.6f text. That is enough to round-trip a
    float32 for coordinates of this magnitude, but the table key has to match
    what the engine holds bit for bit, so the authoritative value is read back
    out of the module's own `.git` and the CSV is checked against it.
    """
    import csv

    # Imported here, not at module scope: map_calibration pulls in PyKotor, and
    # the shipped patcher writes a frozen table instead of re-deriving keys, so
    # it must be able to import this module without that dependency present.
    import map_calibration as mc

    if game is None:
        game = mc.DEFAULT_GAME

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("no corrections in %s" % path)

    by_module = {}
    for r in rows:
        by_module.setdefault(r["module"], []).append(r)

    out, problems = [], []
    for module, mrows in sorted(by_module.items()):
        mod = mc.load_module(os.path.join(game, "modules", module + ".rim"))
        if mod is None:
            problems.append("%s: cannot load module" % module)
            continue
        notes = {n.index: n for n in mod.notes}
        for r in mrows:
            idx = int(r["note_index"])
            note = notes.get(idx)
            if note is None:
                problems.append("%s #%d: no such map note" % (module, idx))
                continue
            key_x, key_y = f32(note.x), f32(note.y)
            if f32(r["old_world_x"]) != key_x or f32(r["old_world_y"]) != key_y:
                problems.append(
                    "%s #%d: CSV key (%r, %r) != module key (%r, %r)"
                    % (module, idx, f32(r["old_world_x"]), f32(r["old_world_y"]),
                       key_x, key_y))
                continue
            out.append({
                "module": module, "index": idx,
                "name": r["name"], "rule": r["rule"],
                "old": (key_x, key_y),
                "new": (f32(r["new_world_x"]), f32(r["new_world_y"])),
                "new_px": r["new_px"], "move_px": r["move_px"],
                "cal": mod.calibration,
            })

    # A duplicate key would make the table ambiguous; the review already proves
    # uniqueness across all 340 notes, so this is a regression guard.
    seen = {}
    for c in out:
        if c["old"] in seen:
            problems.append("duplicate key %r shared by %s #%d and %s #%d"
                            % (c["old"], seen[c["old"]]["module"],
                               seen[c["old"]]["index"], c["module"], c["index"]))
        seen[c["old"]] = c

    if problems:
        raise SystemExit("corrections failed validation:\n  "
                         + "\n  ".join(problems[:20]))
    return out


# --------------------------------------------------------------------------
def build_table(corrections):
    """oldX, oldY, newX, newY as float32, one 16-byte entry per correction."""
    buf = bytearray()
    for c in corrections:
        buf += f32_bytes(c["old"][0]) + f32_bytes(c["old"][1])
        buf += f32_bytes(c["new"][0]) + f32_bytes(c["new"][1])
    return bytes(buf)


def build_code(table_va, table_end_va, resume_va, code_va):
    """The match routine.

    Assembled instruction-by-instruction with keystone (so no ModRM byte is
    hand-encoded), with only the four branch displacements computed here; the
    result is independently disassembled and checked by verify_code().

    Registers: EDX (argument block) and ESI/EDI/EBP are never written. EAX and
    EBX are saved and restored. ECX is dead on entry once the reproduced
    `mov [edx+8],ecx` has run, and is reloaded by the reproduced `mov ecx,eax`
    on the way out.

    Comparison is a plain 32-bit integer compare of the float bits, which is
    exactly the bit-for-bit equality wanted - no FPU involved, so no rounding
    and no x87 state to preserve.
    """
    import keystone

    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)

    def a(text):
        enc, count = ks.asm(text)
        if enc is None or count == 0:
            raise SystemExit("failed to assemble: %s" % text)
        return bytes(enc)

    prologue = (
        a("mov dword ptr [edx + 8], ecx")   # reproduce the hooked instruction
        + a("push eax")
        + a("push ebx")
        + a("mov eax, dword ptr [edx]")     # X bits
        + a("mov ecx, dword ptr [edx + 4]")  # Y bits
        + a("mov ebx, %d" % table_va)
    )
    cmp_x = a("cmp dword ptr [ebx], eax")
    cmp_y = a("cmp dword ptr [ebx + 4], ecx")
    advance = a("add ebx, %d" % ENTRY_BYTES) + a("cmp ebx, %d" % table_end_va)
    found = (
        a("mov eax, dword ptr [ebx + 8]")
        + a("mov dword ptr [edx], eax")
        + a("mov eax, dword ptr [ebx + 12]")
        + a("mov dword ptr [edx + 4], eax")
    )
    epilogue = a("pop ebx") + a("pop eax") + a("mov ecx, eax")

    # Layout (all intra-routine branches are rel8):
    #   scan:  cmp_x  jne next   cmp_y  je found
    #   next:  advance  jb scan  jmp done
    #   found: ...
    #   done:  epilogue  jmp resume
    JCC, JMP8, JMP32 = 2, 2, 5
    scan_off = len(prologue)
    next_off = scan_off + len(cmp_x) + JCC + len(cmp_y) + JCC
    found_off = next_off + len(advance) + JCC + JMP8
    done_off = found_off + len(found)
    end_off = done_off + len(epilogue) + JMP32

    def rel8(frm, to):
        d = to - frm
        if not -128 <= d <= 127:
            raise SystemExit("branch out of rel8 range: %d" % d)
        return struct.pack("<b", d)

    code = bytearray()
    code += prologue
    code += cmp_x
    code += b"\x75" + rel8(len(code) + JCC, next_off)          # jne next
    code += cmp_y
    code += b"\x74" + rel8(len(code) + JCC, found_off)         # je found
    assert len(code) == next_off, (len(code), next_off)
    code += advance
    code += b"\x72" + rel8(len(code) + JCC, scan_off)          # jb scan
    code += b"\xeb" + rel8(len(code) + JMP8, done_off)         # jmp done
    assert len(code) == found_off, (len(code), found_off)
    code += found
    assert len(code) == done_off, (len(code), done_off)
    code += epilogue
    target = resume_va - (code_va + len(code) + JMP32)
    code += b"\xe9" + struct.pack("<i", target)                # jmp resume
    assert len(code) == end_off, (len(code), end_off)
    return bytes(code)


EXPECTED_FLOW = [
    "mov", "push", "push", "mov", "mov", "mov",          # prologue
    "cmp", "jne", "cmp", "je",                            # scan
    "add", "cmp", "jb", "jmp",                            # next
    "mov", "mov", "mov", "mov",                           # found
    "pop", "pop", "mov", "jmp",                           # done
]


def verify_code(code, code_va, table_va, table_end_va, resume_va, quiet=False):
    """Independently disassemble the routine and check it instruction by
    instruction, including that every branch resolves where intended."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    insns = list(md.disasm(code, code_va))
    problems = []
    if len(insns) != len(EXPECTED_FLOW):
        problems.append("expected %d instructions, disassembled %d"
                        % (len(EXPECTED_FLOW), len(insns)))
    for insn, want in zip(insns, EXPECTED_FLOW):
        if insn.mnemonic != want:
            problems.append("0x%X: %s %s - expected %s"
                            % (insn.address, insn.mnemonic, insn.op_str, want))
    if sum(1 for i in insns if i.mnemonic == "jmp" and
           i.op_str == ("0x%x" % resume_va)) != 1:
        problems.append("no single `jmp 0x%X` back to the call site" % resume_va)
    if not any(("0x%x" % table_va) in i.op_str for i in insns):
        problems.append("table base 0x%X never loaded" % table_va)
    if not any(("0x%x" % table_end_va) in i.op_str for i in insns):
        problems.append("table end 0x%X never compared" % table_end_va)
    # nothing may write EDX, ESI, EDI, EBP or ESP
    for i in insns:
        dst = i.op_str.split(",")[0].strip()
        if dst in ("edx", "esi", "edi", "ebp", "esp") and i.mnemonic in (
                "mov", "add", "sub", "lea", "pop", "xor"):
            problems.append("0x%X: %s %s writes %s" % (i.address, i.mnemonic,
                                                       i.op_str, dst))
    if not quiet:
        for i in insns:
            print("      0x%X:  %-6s %s" % (i.address, i.mnemonic, i.op_str))
    return problems


# --------------------------------------------------------------------------
def layout(data, table_len, exe_path=None):
    """(code_va, table_va) for a table of `table_len` bytes in this exe.

    The cave holds the match routine and, if it fits, the table too. Once the
    reviewed table outgrows the cave the table (data only) moves to the region
    pe_space.py reserves at the end of .rsrc; the routine always stays here,
    because that region is not executable.
    """
    code_va = CAVE_VA
    table_va = (CAVE_VA + 0x80) & ~0xF     # code first, table 16-byte aligned
    if table_va + table_len > FREE_END_VA:
        reserved = pe_space.table_va(data)
        if reserved is None:
            raise SystemExit(
                "the table needs %d B but only %d B of cave are left, and no "
                "region is reserved in %s.\nRun:  python tools/pe_space.py apply "
                "\"%s\"" % (table_len, FREE_END_VA - table_va, exe_path, exe_path))
        table_va = reserved
    return code_va, table_va


def plan(exe_path):
    corrections = load_corrections()
    table = build_table(corrections)
    code_va = CAVE_VA
    table_va = (CAVE_VA + 0x80) & ~0xF
    if table_va + len(table) > FREE_END_VA and exe_path:
        with open(exe_path, "rb") as fh:
            code_va, table_va = layout(bytearray(fh.read()), len(table), exe_path)
    code = build_code(table_va, table_va + len(table), RESUME_VA, code_va)
    if len(code) > (CAVE_VA + 0x80) - code_va:
        raise SystemExit("code (%d B) overruns the table start" % len(code))
    table_end = table_va + len(table)

    print("corrections:      %d  (validated against the real module files)" % len(corrections))
    print("hook:             0x%X  (5 bytes: %s)" % (HOOK_VA, HOOK_DEFAULT.hex()))
    print("resume:           0x%X" % RESUME_VA)
    print("match routine:    0x%X .. 0x%X  (%d bytes)" % (code_va, code_va + len(code), len(code)))
    print("table:            0x%X .. 0x%X  (%d entries x %d B = %d bytes)"
          % (table_va, table_end, len(corrections), ENTRY_BYTES, len(table)))
    in_cave = table_va < FREE_END_VA
    if in_cave:
        print("free tail ends:   0x%X  -> %d bytes still unused"
              % (FREE_END_VA, FREE_END_VA - table_end))
        if table_end > FREE_END_VA:
            raise SystemExit("table overruns the verified free region")
    else:
        print("table location:   reserved region (pe_space), NOT the .text cave")
        with open(exe_path, "rb") as fh:
            data = bytearray(fh.read())
        region_rva, usable = pe_space.find_region(data)
        region_end = pe_space.IMAGE_BASE + region_rva + pe_space.HEADER_BYTES + usable
        print("region ends:      0x%X  -> %d bytes still unused"
              % (region_end, region_end - table_end))
        if table_end > region_end:
            raise SystemExit("table overruns the reserved region")

    print("\n  match routine disassembly:")
    problems = verify_code(code, code_va, table_va, table_end, RESUME_VA)
    if problems:
        print("\n  CODE PROBLEMS:")
        for p in problems:
            print("    " + p)
        raise SystemExit(1)
    print("\n  code verified: %d instructions, branches resolve, EDX/ESI/EDI/EBP/ESP "
          "never written" % len(EXPECTED_FLOW))

    if exe_path:
        check_target(exe_path, code_va, len(code), table_va, len(table))
    print("\n  biggest corrections in the table:")
    for c in sorted(corrections, key=lambda c: -float(c["move_px"]))[:8]:
        print("    %-12s #%-3d %-24s %5s px -> px %s"
              % (c["module"], c["index"], c["name"][:24], c["move_px"], c["new_px"]))
    return corrections, code, table, code_va, table_va


def check_target(exe_path, code_va, code_len, table_va, table_len):
    with open(exe_path, "rb") as fh:
        data = bytearray(fh.read())
    print("\n  target: %s (%d bytes)" % (exe_path, len(data)))
    off = HOOK_VA - IMAGE_BASE
    current = bytes(data[off:off + 5])
    if current == HOOK_DEFAULT:
        print("    hook site holds the expected original bytes")
    else:
        print("    hook site holds %s, expected %s  <== REFUSING"
              % (current.hex(), HOOK_DEFAULT.hex()))
        raise SystemExit(1)
    # Both destinations are checked separately now: once the table outgrew the
    # cave they are in different sections, so one span no longer covers both.
    for label, va, length in (("match routine", code_va, code_len),
                              ("table", table_va, table_len)):
        start = va_to_off(data, va)
        region = data[start:start + length]
        if set(region) == {0}:
            print("    %s destination 0x%X..0x%X is all zero (%d bytes)"
                  % (label, va, va + length, length))
        else:
            print("    %s destination is NOT free (%d nonzero bytes)  <== REFUSING"
                  % (label, sum(1 for b in region if b)))
            raise SystemExit(1)


def va_to_off(data, va):
    """File offset for a VA. Only .text is flat-mapped, so this must go through
    the section table for anything outside it (the table's reserved region)."""
    return pe_space.rva_to_off(data, va - IMAGE_BASE)


def apply(exe_path):
    corrections, code, table, code_va, table_va = plan(exe_path)
    table_end = table_va + len(table)

    backup = backup_paths.make_backup(exe_path, ".pre-notetable-backup")

    with open(exe_path, "rb") as fh:
        data = bytearray(fh.read())

    code_off = va_to_off(data, code_va)
    table_off = va_to_off(data, table_va)
    hook_off = HOOK_VA - IMAGE_BASE
    hook_jmp = b"\xe9" + struct.pack("<i", code_va - (HOOK_VA + 5))

    data[code_off:code_off + len(code)] = code
    data[table_off:table_off + len(table)] = table
    data[hook_off:hook_off + 5] = hook_jmp

    with open(exe_path, "wb") as fh:
        fh.write(data)
    print("wrote %s" % exe_path)

    # verify what is actually on disk, not what we think we wrote
    with open(exe_path, "rb") as fh:
        written = bytes(fh.read())
    ok = True
    if bytes(written[hook_off:hook_off + 5]) != hook_jmp:
        print("  MISMATCH at hook site"); ok = False
    if bytes(written[code_off:code_off + len(code)]) != code:
        print("  MISMATCH in the match routine"); ok = False
    if bytes(written[table_off:table_off + len(table)]) != table:
        print("  MISMATCH in the table"); ok = False

    print("\nreadback disassembly of the hook:")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for i in md.disasm(bytes(written[hook_off:hook_off + 5]), HOOK_VA):
        print("      0x%X:  %-6s %s" % (i.address, i.mnemonic, i.op_str))
    print("readback disassembly of the match routine:")
    problems = verify_code(bytes(written[code_off:code_off + len(code)]),
                           code_va, table_va, table_end, RESUME_VA)
    if problems:
        ok = False
        for p in problems:
            print("    " + p)

    # spot-check the table as the CPU will read it
    print("\nreadback table spot-check (first 3 and the largest correction):")
    picks = corrections[:3] + [max(corrections, key=lambda c: float(c["move_px"]))]
    for c in picks:
        i = corrections.index(c)
        raw = bytes(written[table_off + i * 16:table_off + (i + 1) * 16])
        ox, oy, nx, ny = struct.unpack("<ffff", raw)
        good = (ox, oy) == c["old"] and (nx, ny) == c["new"]
        px = c["cal"].to_pixel(nx, ny)
        print("      %-12s #%-3d %-22s (%.4f,%.4f)->(%.4f,%.4f) px%s  %s"
              % (c["module"], c["index"], c["name"][:22], ox, oy, nx, ny, px,
                 "OK" if good else "MISMATCH"))
        if not good:
            ok = False

    if ok:
        print("\nreadback verified byte-exact. NOT yet confirmed in game - per this "
              "project's rules, check BOTH the in-menu Area Map and the HUD minimap, "
              "and confirm player/party markers are unmoved, before trusting this.")
        print("Revert with:  copy \"%s\" \"%s\"" % (backup, exe_path))
        return 0
    print("\nREADBACK MISMATCH - restore from %s before running the game." % backup)
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("plan", "apply"):
        print(__doc__)
        raise SystemExit(2)
    if sys.argv[1] == "plan":
        plan(sys.argv[2] if len(sys.argv) > 2 else None)
        raise SystemExit(0)
    if len(sys.argv) < 3:
        print("usage: note_table_patch.py apply <EXE>")
        raise SystemExit(2)
    raise SystemExit(apply(sys.argv[2]))
