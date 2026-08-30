"""
Reusable disassembly/xref helpers for swkotor.exe reverse-engineering.

Every past capstone/pefile investigation this session (finding the tile-size
fdivr operands, tracing the marker-calibration constructor/transform, the
`SUB EAX, imm32` 640/480 scan) was a one-off interactive script that was never
saved - so each new question meant re-deriving the same plumbing from
scratch. This module is that plumbing, saved once and reused.

Confirmed layout (see NOTES.md "Disassembly investigation started"): for this
exe, .text/.rdata/.data all have PointerToRawData == VirtualAddress, so a
flat `VA = IMAGE_BASE + file_offset` mapping holds everywhere - no need to
walk section headers for every lookup. IMAGE_BASE matches hires_patch.py.

Usage (see `if __name__ == "__main__"` at the bottom):
    python disasm_helpers.py refs   <exe> <va_hex>              # who references this address?
    python disasm_helpers.py disasm <exe> <va_hex> [before] [after]  # disassemble around a VA
    python disasm_helpers.py func   <exe> <va_hex>              # nearest function prologue at/before VA

Requires `capstone` and `pefile` (already installed in this environment per
NOTES.md's "Disassembly investigation started" section).
"""

import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

IMAGE_BASE = 0x400000

# Common x86 function-prologue byte patterns, checked longest-first.
PROLOGUE_PATTERNS = [
    bytes.fromhex("558bec"),  # push ebp; mov ebp, esp
    bytes.fromhex("55894424"),  # push ebp; mov [esp+N], ebp variants (rare, kept short deliberately)
]


def load_exe(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def va_to_off(va):
    return va - IMAGE_BASE


def off_to_va(off):
    return off + IMAGE_BASE


def find_references(data, target_va, start=0, end=None):
    """Scan `data` for every 4-byte little-endian occurrence of `target_va`.

    This is the technique that found the tile-size and marker-calibration
    float constants' referencing instructions: absolute-addressed x86
    operands (disp32 in `mov`/`fdivr`/`fmul dword ptr [addr]`, immediate
    pushes of a pointer, etc.) store the raw VA as a little-endian dword, so
    a byte-string search for that dword finds every reference regardless of
    which instruction it's embedded in. Returns a list of FILE OFFSETS where
    the 4-byte match starts (i.e. the disp32/immediate field itself, not the
    instruction's start byte).
    """
    needle = struct.pack("<I", target_va)
    end = len(data) if end is None else end
    hits = []
    pos = start
    while True:
        idx = data.find(needle, pos, end)
        if idx == -1:
            break
        hits.append(idx)
        pos = idx + 1
    return hits


def disasm_window(data, va, before=32, after=32):
    """Disassemble instructions spanning [va-before, va+after) file bytes.

    x86 is variable-length, so there's no guaranteed instruction boundary at
    `va - before`. This linearly disassembles from that point forward and
    returns every instruction capstone finds, including ones that start
    before `va` (for context) and end after `va + after`. If the start point
    lands mid-instruction, the first instruction or two may be garbage -
    always sanity-check against a known-good reference (e.g. does one of the
    returned instructions land exactly on `va`?).
    """
    off = va_to_off(va)
    start = max(0, off - before)
    stop = min(len(data), off + after)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False
    out = []
    for insn in md.disasm(bytes(data[start:stop]), off_to_va(start)):
        out.append(insn)
    return out


def print_window(data, va, before=32, after=32):
    for insn in disasm_window(data, va, before, after):
        marker = " <=== " if insn.address <= va < insn.address + insn.size else "      "
        print(f"  0x{insn.address:X}:{marker}{insn.mnemonic} {insn.op_str}")


def find_function_start(data, va, max_back=0x2000):
    """Scan backward from `va` for the nearest recognizable prologue byte
    pattern. Best-effort only - a miss just means "not found within
    max_back", not "no function exists here". Cross-check with known
    callers/vtable entries rather than trusting this alone.
    """
    off = va_to_off(va)
    lo = max(0, off - max_back)
    for candidate in range(off, lo, -1):
        for pat in PROLOGUE_PATTERNS:
            if data[candidate:candidate + len(pat)] == pat:
                return off_to_va(candidate)
    return None


def report_references(data, target_va, context=24):
    """Convenience: find every reference to `target_va` and print a
    disassembly window around each, plus the nearest prologue before it (a
    cheap way to bucket references by "which function is this in").
    """
    hits = find_references(data, target_va)
    print(f"{len(hits)} reference(s) to 0x{target_va:X}:")
    for h in hits:
        ref_va = off_to_va(h)
        # the disp32 field sits inside the instruction; back up a few bytes
        # to disassemble from the instruction's actual start
        instr_va = ref_va - 6
        func_va = find_function_start(data, instr_va)
        print(f"\n--- operand at VA 0x{ref_va:X} (file 0x{h:X}), "
              f"nearest prologue: {'0x%X' % func_va if func_va else 'not found'} ---")
        print_window(data, instr_va, before=context, after=context)


def find_direct_calls(data, target_va, start_va, end_va):
    """Linearly disassemble [start_va, end_va) and return the VA of every
    `call`/`jmp` instruction whose immediate target equals `target_va`.

    Unlike `find_references` (which only catches absolute-addressed operands,
    e.g. `[disp32]` memory reads), this catches near CALL/JMP rel32
    instructions, which encode a *relative* displacement - a raw byte search
    for the target address's bytes can never find these. This is the
    rigorous way to answer "who calls this function", as opposed to the
    informal/incomplete manual searches logged earlier in NOTES.md.
    """
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False
    off_start, off_end = va_to_off(start_va), va_to_off(end_va)
    hits = []
    for insn in md.disasm(bytes(data[off_start:off_end]), start_va):
        if insn.mnemonic in ("call", "jmp") and insn.op_str.startswith("0x"):
            try:
                target = int(insn.op_str, 16)
            except ValueError:
                continue
            if target == target_va:
                hits.append(insn.address)
    return hits


def find_calls_bruteforce(data, target_va, start_off, end_off):
    """Byte-level scan for `E8 <rel32>` (near CALL rel32) at EVERY offset,
    not just capstone's chosen instruction boundaries. A single linear
    disassembly pass can drift out of sync after hitting embedded data (jump
    tables, string literals) inside a code section and silently misparse
    everything after - this catches call sites a drifted linear pass would
    miss. False positives are vanishingly unlikely (all 4 rel32 bytes would
    have to coincidentally compute the exact target VA), so any hit here not
    already found by `find_direct_calls` is worth a direct look.
    """
    hits = []
    for pos in range(start_off, end_off - 4):
        if data[pos] != 0xE8:
            continue
        (rel32,) = struct.unpack_from("<i", data, pos + 1)
        insn_va = off_to_va(pos)
        target = insn_va + 5 + rel32
        if target == target_va:
            hits.append(insn_va)
    return hits


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"usage:\n"
              f"  {sys.argv[0]} refs   <exe> <va_hex>\n"
              f"  {sys.argv[0]} disasm <exe> <va_hex> [before] [after]\n"
              f"  {sys.argv[0]} func   <exe> <va_hex>\n"
              f"  {sys.argv[0]} calls  <exe> <va_hex> [start_va_hex] [end_va_hex]")
        sys.exit(1)

    cmd, exe_path, va_hex = sys.argv[1], sys.argv[2], sys.argv[3]
    va = int(va_hex, 16)
    exe_data = load_exe(exe_path)

    if cmd == "refs":
        report_references(exe_data, va)
    elif cmd == "disasm":
        before = int(sys.argv[4]) if len(sys.argv) > 4 else 32
        after = int(sys.argv[5]) if len(sys.argv) > 5 else 32
        print_window(exe_data, va, before, after)
    elif cmd == "func":
        found = find_function_start(exe_data, va)
        print(f"nearest prologue: 0x{found:X}" if found else "not found")
    elif cmd == "calls":
        start_va = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x401000
        end_va = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x73D000
        linear_hits = set(find_direct_calls(exe_data, va, start_va, end_va))
        brute_hits = set(find_calls_bruteforce(exe_data, va, va_to_off(start_va), va_to_off(end_va)))
        all_hits = sorted(linear_hits | brute_hits)
        print(f"{len(all_hits)} call site(s) to 0x{va:X} in [0x{start_va:X}, 0x{end_va:X}) "
              f"(linear-disasm found {len(linear_hits)}, brute-force found {len(brute_hits)}):")
        for h in all_hits:
            func = find_function_start(exe_data, h)
            tag = "" if h in linear_hits and h in brute_hits else " (brute-force only - check for disasm drift!)"
            print(f"  0x{h:X}  (nearest prologue: {'0x%X' % func if func else 'not found'}){tag}")
    else:
        print(f"unknown command {cmd!r}")
        sys.exit(1)
