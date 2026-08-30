"""Prove, from the bytes actually on disk, that the patch landed and nothing else did.

Two independent questions, both answered against a fresh read of the file:

1. **Is everything we meant to write there?** Each layer is re-checked at its own
   offsets, and the injected code is re-disassembled with capstone rather than
   trusted from the write call - the same standard the development tools hold
   themselves to.
2. **Is anything we did NOT mean to write there?** Every byte that differs from
   the pre-patch image must fall inside a range this patcher declared. That is
   the check that would catch a bad offset table, a partially-applied earlier
   run, or a layer reaching somewhere it has no business being.
"""
from __future__ import annotations

import struct

from . import _toolpath  # noqa: F401
from . import detect

import capstone
import hires_patch
import note_table_patch as ntp
import pe_space

CHUNK = 4096


def declared_ranges(before, code_va, table_va, code_len, table_len):
    """Every (start, end) file range this patcher is allowed to change."""
    hp = hires_patch
    out = []

    # SKIP_SITES is deliberately absent: a write there would be a stray.
    out += [(o, o + struct.calcsize(tpl))
            for _key, o, tpl, _d in detect.scale_sites()]
    out += [(s, s + 4) for s in hp.PRIVATE_FLOAT_SLOTS.values()]
    out += [(o, o + 4) for axis in hp.BIGMAP_FLOAT_OPERANDS
            for o in hp.BIGMAP_FLOAT_OPERANDS[axis]]
    out += [(hp.MARKER_KX_SLOT, hp.MARKER_KX_SLOT + 4),
            (hp.MARKER_KY_SLOT, hp.MARKER_KY_SLOT + 4)]

    for va, length in ((hp.MARKER_HOOK_VA, len(hp.MARKER_HOOK_JMP)),
                       (hp.MARKER_CAVE_VA, len(hp.MARKER_CAVE_BYTES)),
                       (hp.PARTY_HOOK_VA, len(hp.PARTY_HOOK_JMP)),
                       (hp.PARTY_CAVE_VA, len(hp.PARTY_CAVE_BYTES)),
                       (hp.PLAYER_HOOK_VA, len(hp.PLAYER_HOOK_DEFAULT)),
                       (hp.PLAYER_CAVE_VA, len(hp.PLAYER_CAVE_BYTES)),
                       (ntp.HOOK_VA, len(ntp.HOOK_DEFAULT))):
        off = va - hp.IMAGE_BASE
        out.append((off, off + length))

    # The match routine is in .text, which exists in both images. The table is
    # not: it lives in the region pe_space appends past the old EOF, so the
    # caller adds that range separately.
    code_off = ntp.va_to_off(before, code_va)
    out.append((code_off, code_off + code_len))

    # PE header fields pe_space.extend() rewrites
    last = pe_space.sections(before)[-1]
    _pe_off, _nsec, _optsz, opt, _sec = pe_space._pe(before)
    out += [(last["hdr"] + 8, last["hdr"] + 12),
            (last["hdr"] + 16, last["hdr"] + 20),
            (opt + 56, opt + 60)]
    return sorted(out)


def unexpected_changes(before, after, allowed):
    """File offsets that changed but were not declared. Chunk-compares first, so
    a 4 MB image costs a handful of C-level comparisons, not 4 million Python ones.
    """
    bad = []
    n = min(len(before), len(after))
    for base in range(0, n, CHUNK):
        end = min(base + CHUNK, n)
        if before[base:end] == after[base:end]:
            continue
        for i in range(base, end):
            if before[i] != after[i] and not any(s <= i < e for s, e in allowed):
                bad.append(i)
                if len(bad) > 32:
                    return bad
    return bad


def check(before, after, width, height, table, code_va, table_va):
    """[(ok, label), ...] - every post-write check, in the order run."""
    hp = hires_patch
    results = []

    def ok(label, good):
        results.append((bool(good), label))

    ok("file size grew by exactly the reserved region (%d bytes)"
       % pe_space.REGION_BYTES, len(after) - len(before) == pe_space.REGION_BYTES)

    # --- 1. mapscale -----------------------------------------------------
    values = hp.map_scale_values(width, height)
    good = True
    for key, off, tpl, _default in detect.scale_sites():
        good &= struct.unpack_from(tpl, after, off)[0] == hp._round_half_up(values[key])
    ok("all %d map-scale constants hold the values for %dx%d"
       % (detect.SCALE_SITE_COUNT, width, height), good)

    good = True
    for axis, slot in hp.PRIVATE_FLOAT_SLOTS.items():
        want = values["map_offsets_x" if axis == "x" else "map_offsets_y"]
        got = struct.unpack_from("<f", after, slot)[0]
        good &= abs(got - want) < 0.01
        for opnd in hp.BIGMAP_FLOAT_OPERANDS[axis]:
            good &= struct.unpack_from("<I", after, opnd)[0] == hp.IMAGE_BASE + slot
    ok("Area Map reads its own scaled tile-size floats", good)
    ok("the shared 440.0/256.0 constants are untouched, so the HUD minimap still works",
       struct.unpack_from("<f", after, hp.SHARED_FLOAT_X)[0] == 440.0 and
       struct.unpack_from("<f", after, hp.SHARED_FLOAT_Y)[0] == 256.0)

    # --- 2. the three marker caves --------------------------------------
    for label, va, want in (
            ("map-note marker", hp.MARKER_HOOK_VA, hp.MARKER_HOOK_JMP),
            ("party marker", hp.PARTY_HOOK_VA, hp.PARTY_HOOK_JMP),
            ("player marker", hp.PLAYER_HOOK_VA,
             hp.PLAYER_HOOK_JMP + hp.PLAYER_HOOK_NOP_PAD)):
        off = va - hp.IMAGE_BASE
        ok("%s hook at 0x%X" % (label, va),
           bytes(after[off:off + len(want)]) == want)
    for label, va, want in (
            ("map-note marker", hp.MARKER_CAVE_VA, hp.MARKER_CAVE_BYTES),
            ("party marker", hp.PARTY_CAVE_VA, hp.PARTY_CAVE_BYTES),
            ("player marker", hp.PLAYER_CAVE_VA, hp.PLAYER_CAVE_BYTES)):
        off = va - hp.IMAGE_BASE
        ok("%s routine at 0x%X (%d bytes)" % (label, va, len(want)),
           bytes(after[off:off + len(want)]) == want)

    # --- 3. reserved region ---------------------------------------------
    region = pe_space.find_region(after)
    ok("8 KB region reserved at the end of .rsrc", region is not None)
    last = pe_space.sections(after)[-1]
    ok("the last section's data still ends at the end of the file",
       last["rawptr"] + last["rawsize"] == len(after))
    ok("the 'Hellspawn Reborn' watermark at 0xAC0 is preserved",
       bytes(after[0xAC0:0xAD0]) == bytes(before[0xAC0:0xAD0]))

    # --- 4. note table + match routine ----------------------------------
    hook_off = ntp.HOOK_VA - hp.IMAGE_BASE
    want_jmp = b"\xe9" + struct.pack("<i", code_va - (ntp.HOOK_VA + 5))
    ok("map-note hook at 0x%X jumps to the match routine" % ntp.HOOK_VA,
       bytes(after[hook_off:hook_off + 5]) == want_jmp)

    code_off = ntp.va_to_off(after, code_va)
    table_off = ntp.va_to_off(after, table_va)
    code = ntp.build_code(table_va, table_va + len(table), ntp.RESUME_VA, code_va)
    on_disk = bytes(after[code_off:code_off + len(code)])
    ok("match routine at 0x%X is byte-exact" % code_va, on_disk == code)
    problems = ntp.verify_code(on_disk, code_va, table_va, table_va + len(table),
                               ntp.RESUME_VA, quiet=True)
    ok("match routine re-disassembles correctly (%d instructions, branches resolve)"
       % len(list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
                  .disasm(on_disk, code_va))), not problems)

    ok("%d map-note corrections at 0x%X are byte-exact"
       % (len(table) // ntp.ENTRY_BYTES, table_va),
       bytes(after[table_off:table_off + len(table)]) == table)

    # read the first and last entry back as the CPU will
    good = True
    for i in (0, len(table) // ntp.ENTRY_BYTES - 1):
        raw = bytes(after[table_off + i * 16:table_off + (i + 1) * 16])
        good &= raw == table[i * 16:(i + 1) * 16] and len(struct.unpack("<ffff", raw)) == 4
    ok("first and last correction read back as valid float pairs", good)

    # --- 5. nothing else changed ----------------------------------------
    allowed = declared_ranges(before, code_va, table_va, len(code), len(table))
    allowed.append((len(before), len(after)))          # the appended region
    if table_off >= len(before):
        pass                                           # table is in that region
    else:
        allowed.append((table_off, table_off + len(table)))
    stray = unexpected_changes(before, after, allowed)
    ok("no byte outside this patcher's declared ranges was changed"
       + ("" if not stray else " (first stray: 0x%X)" % stray[0]), not stray)

    return results
