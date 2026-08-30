"""
Port of ndix UR's hires_patcher.pl (GPLv3) from the "KotOR High Resolution
Menus" package (deadlystream.com/files/file/1159), reimplemented in Python
so we understand and control every byte we write instead of running someone
else's compiled binary.

What it does: the Odyssey engine bounds its GUI/camera coordinate system
with hardcoded +-640 / +-480 constants (the base 640x480 canvas) at a
handful of fixed file offsets, one offset set per known exe build. This
overwrites those constants with the real target width/height so the GUI
system's own internal bounds actually match the screen instead of clamping
everything into a small box. Separate from (and required in addition to)
the resolution-gate patch UniWS applies.

Every offset is verified against its known default value before writing -
if the exe doesn't match a known build closely enough, this refuses to
patch rather than guessing.
"""

import math
import shutil

import backup_paths
import struct
import sys

DEFAULTS = {
    "negative_offsets_x": -640,
    "negative_offsets_y": -480,
    "positive_offsets_x": 640,
    "positive_offsets_y": 480,
}

# offset, one list per known exe build: gog, 4cd ITA, 4cd POL, macOS
#
# BUG FOUND AND FIXED 2026-08-23: negative_offsets_x/y each hold TWO offsets
# per exe build in the original hires_patcher.pl (one for menu buttons, one
# for list/scrollbar hit-testing - confirmed against the official k1hrm
# README's manual hex-edit instructions, which document them as two
# separate, deliberate edits: "this will fix being able to click menu
# buttons" at 0xB6C7/0xB6DA, and "this will fix being able to scroll and
# click list items (like save games)" at 0xBA6C/0xBA83 (gog build). This
# port previously kept only the FIRST offset of each pair and silently
# dropped the second - meaning every exe we've built with this tool patched
# button hit-testing but left list/scrollbar hit-testing (0xBA6C/0xBA83 for
# gog) untouched at its vanilla -640/-480 default the entire time. This is
# almost certainly the actual cause of the "buttons work, lists don't"
# click bug investigated at length this session - confirmed via read-back:
# both offsets were still sitting at -640/-480 in the exe we'd been testing
# against. positive_offsets_x/y were NOT affected - those arrays hold
# multiple *distinct* call sites per build already, not accidentally-
# dropped pairs, and were fully (correctly) flattened already.
OFFSETS = {
    "negative_offsets_x": [0xB6C7, 0xBA6C, 0xB537, 0xB8DC, 0xB7B7, 0xBB5C],
    "negative_offsets_y": [0xB6DA, 0xBA83, 0xB54A, 0xB8F3, 0xB7CA, 0xBB73],
    "positive_offsets_x": [0xAA65, 0x292959, 0x2928B3, 0xA895, 0xAB05, 0xBD9424, 0xBD949B, 0xBDA055],
    "positive_offsets_y": [0xAA85, 0x29296B, 0x2928C3, 0xA8B5, 0xAB25, 0xBD9449, 0xBD94B3, 0xBDA06D],
}

DIALOG_LETTERBOX_OFFSETS = {
    # offset -> default raw uint32 (as originally stored, gog variant only for now)
    0x355788: 0x3EDB6DB9,
}

# Map-screen scaling ("mapscale" in the original hires_patcher.pl - present in
# that script but hardcoded OFF there (opt{mapscale}=0), so it never actually
# runs even though the logic is fully implemented. Ported here since we
# understand exactly what it does: without it, the tactical area map ("map.gui")
# scales its frame but not the map image inside it.
#
# TRIED AND REVERTED 2026-08-23 (first minimap attempt): excluding
# map_projection_offsets_x (0x29505C) + one map_offsets_y entry (0x295064)
# from scaling. Theory was that this (512,256) pair belonged to the HUD
# minimap. WRONG - it didn't fix the minimap and it broke the big map's room
# geometry. Both offsets are back in the scaled set below. Root cause turned
# out to be the float constants instead - see below.
#
# ROOT CAUSE FOUND 2026-08-23 (second attempt, via capstone disassembly):
# `map_offsets_float_x/y` are NOT private to the Area Map screen. They are two
# constants in .rdata (440.0f @ 0x347748, 256.0f @ 0x3455D4) that are read by
# FOUR different subsystems, confirmed by searching the whole .text for the
# 4-byte LE encoding of their addresses:
#   VA 0x508C40  - the ARE (area file) loader   (binds "OnEnter"/"Creator_ID"/"Tag")
#   VA 0x578F10  - shared map-coordinate helper (the integer cluster below)
#   VA 0x6880C0  - HUD map drawing, called from 0x68B089, inside the class whose
#                  init at VA 0x68BF50 binds "mipc28x6"/"mipc216x12"/"mipc210x7"
#                  -> definitively the in-game HUD (mipc GUI family) = MINIMAP
#   VA 0x6943D0  - a virtual method (vtable entry at 0x754770) in the class whose
#                  init at VA 0x694D50 binds "LBL_Map"/"LBL_MapNote"/"LBL_COMPASS"/
#                  "BTN_PRTYSLCT" -> definitively map.gui = the AREA MAP SCREEN
# Both map drawers compute a tile size the same way - `440.0 / gridCountX` and
# `256.0 / gridCountY` - from these SHARED constants. hires_patcher.pl's mapscale
# rewrites the constants in place, so scaling the Area Map necessarily rescales
# the HUD minimap too. But the minimap's own GUI box (LBL_MAP in mipc*.gui) is a
# FIXED 512x512 at every vanilla resolution (verified across all 4 buckets, and
# k1hrm leaves it alone) - so its tiles get drawn at full-screen scale inside a
# small fixed box and land outside it: the minimap renders black with only the
# player marker (drawn by different, position-clamped code) still visible.
# That is almost certainly why ndix UR shipped mapscale hardcoded OFF - in-place
# constant patching, which is all that patcher does, genuinely cannot fix one
# without breaking the other.
#
# FIX: stop rewriting the shared constants. Give the Area Map screen its own
# private scaled copies in unused .rdata padding, and redirect only ITS two
# instruction operands to them (see BIGMAP_FLOAT_* below). The HUD minimap keeps
# reading the untouched originals, so it renders exactly as it does with mapscale
# off. xoreos (the open-source Odyssey re-implementation) independently documents
# the KotOR minimap quad as 512x256 in map space, consistent with this reading.
MAP_OFFSETS = {
    # key: (offsets, struct format, default value)
    "map_projection_offsets_x": ([0x29505C], "<h", 512),
    "map_grid": ([0x17906F], "<h", 32),
    "map_offsets_x": ([0x179009, 0x179344, 0x179377, 0x17937E, 0x178E9B, 0x178F15, 0x295082], "<h", 440),
    "map_offsets_y": ([0x17901A, 0x179358, 0x179383, 0x17938A, 0x178EA6, 0x178F24, 0x295064, 0x29508A], "<h", 256),
}

# The shared .rdata float constants - deliberately LEFT AT THEIR VANILLA VALUES
# so the HUD minimap keeps working (see the root-cause note above).
SHARED_FLOAT_X = 0x347748  # 440.0f, VA 0x747748
SHARED_FLOAT_Y = 0x3455D4  # 256.0f, VA 0x7455D4

# disp32 operand fields of the `fdivr`/`fmul dword ptr [<shared const>]`
# instructions that need to read our private scaled copies instead of the
# shared originals. Two groups:
#
# 1) Area Map draw method (VA 0x6943D0) tile-size divisions:
#      VA 0x6944A8: d8 3d 48 77 74 00   fdivr dword ptr [0x747748]  -> disp32 +2
#      VA 0x6944C4: d8 3d d4 55 74 00   fdivr dword ptr [0x7455d4]  -> disp32 +2
#
# 2) ARE-loader calibration setup (VA ~0x509d00-0x509de0, single caller into
#    0x578C60, which builds the marker world->pixel calibration object read by
#    0x578E00). Converts each area's MapPt1X/Y and MapPt2X/Y into map-texture
#    PIXEL space at area-load time:
#      VA 0x509d1b: fmul dword ptr [0x747748]  -> disp32 at 0x509d1d
#      VA 0x509d58: fmul dword ptr [0x7455d4]  -> disp32 at 0x509d5a
#      VA 0x509d97: fmul dword ptr [0x747748]  -> disp32 at 0x509d99
#      VA 0x509dd6: fmul dword ptr [0x7455d4]  -> disp32 at 0x509dd8
#
# TRIED TWICE, REVERTED BOTH TIMES (most recently 2026-08-23): redirecting
# this group DOES fix Area Map marker tracking, but breaks the HUD minimap
# every time it's been deployed - confirmed reproducible, not a fluke.
#
# First attempt: reverted on the theory that 0x578E00/0x578C60 might be
# called by HUD code too. Second attempt this session: that theory was
# EXHAUSTIVELY DISPROVEN first (tools/emulate_map_ctor.py showed the marker
# fields and the HUD's grid fields are fed by disjoint arguments;
# tools/disasm_helpers.py's `calls` command found, via brute-force
# opcode-level scanning immune to disassembly drift, that 0x578C60 has
# exactly 1 caller and 0x578E00 has exactly 4, ALL inside the Area Map's own
# draw method, none in HUD code) - yet deploying it regressed the minimap
# again anyway. New clue from that regression: the minimap didn't just stay
# black, it PARTIALLY self-corrected (wrong region, wrong player-marker
# position) after the player walked - meaning some HUD per-movement update
# function reads this calibration data INLINE (or redoes the same math
# itself) without ever calling a shared function, which is why no
# caller-graph search could find it. See NOTES.md ("STARTING POINT FOR NEXT
# SESSION: Area Map marker bug" at the top, and "Area Map marker fix" search
# for the full history) before attempting this again.
BIGMAP_FLOAT_OPERANDS = {
    "x": [0x2944AA],
    "y": [0x2944C6],
}

# Where the private scaled copies go: 4-byte-aligned slots inside .rdata's
# tail padding (1026 confirmed-zero bytes from file 0x38CBFE to 0x38D000).
# .rdata has PointerToRawData == VirtualAddress, so VA = 0x400000 + file offset,
# and the whole raw range is mapped (VirtualSize 0x4FBFE rounds up to 0x50000).
PRIVATE_FLOAT_SLOTS = {"x": 0x38CC00, "y": 0x38CC04}
IMAGE_BASE = 0x400000


def find_map_matches(data):
    """Per-offset default check, same spirit as find_matches - map fields are
    never a hard gate (matches the original script's behavior: even if none
    of these match, the core patch still proceeds; each offset is patched
    independently if and only if its current value equals its known default).
    """
    matches = {}
    for key, (offs, tpl, default) in MAP_OFFSETS.items():
        size = struct.calcsize(tpl)
        found = []
        for off in offs:
            if off + size > len(data):
                continue
            (val,) = struct.unpack_from(tpl, data, off)
            if val == default:
                found.append(off)
        matches[key] = found
    return matches


def _round_half_up(x):
    """Perl's `int(x + 0.5)`, not Python's banker's `round()`.

    They disagree only on exact .5 cases, and the only one k1hrm 1.5 can
    produce is 1400x1050 (440*kx = 962.5): `round()` gives 962, k1hrm's own
    `.gui` box says 963. Harmless at every other resolution, wrong at that one.
    See RELEASE_PLAN.md section 2.4.
    """
    return math.floor(x + 0.5)


def map_scale_values(width, height):
    """The four scaled int16 values for this resolution, unrounded.

    One definition, so the patcher can check what it wrote (and what a later
    run finds already there) against the same formula that wrote it.
    """
    return {
        "map_projection_offsets_x": width * (512.0 / 640.0),
        "map_offsets_x": width * (440.0 / 640.0),
        "map_offsets_y": height * (256.0 / 480.0),
        "map_grid": height * (32.0 / 480.0),
    }


def patch_map_scale(data, width, height):
    """Mutates data in place. Formulas exactly mirror hires_patcher.pl's
    mapscale branch (including its apparent quirk: map_projection_offsets_x,
    map_offsets_x, and map_offsets_float_x all end up using the SAME
    width*(512/640) ratio in the original script, not the 440/640 ratio their
    default value's name would suggest - the 440/640 line is dead code there,
    immediately overwritten before use. Replicated faithfully rather than
    'corrected', since the original is the known-working reference.)
    """
    matches = find_map_matches(data)
    # NOTE: hires_patcher.pl actually scales map_projection_offsets_x,
    # map_offsets_x, AND map_offsets_float_x all by the SAME width*(512/640)
    # ratio - a dead-code bug there (a width*(440/640) line is computed and
    # immediately overwritten before use). Originally replicated faithfully;
    # confirmed wrong in-game (map rendered ~288px off-center at 2560 width)
    # and corrected here: map_offsets_x/float_x use their own default's
    # implied 440/640 ratio, map_projection_offsets_x keeps 512/640 since
    # that matches ITS OWN default.
    v = map_scale_values(width, height)
    projection_ratio_value = v["map_projection_offsets_x"]
    offsets_ratio_value = v["map_offsets_x"]
    y_ratio_value = v["map_offsets_y"]

    for key in ("map_projection_offsets_x", "map_offsets_x",
                "map_offsets_y", "map_grid"):
        for off in matches[key]:
            struct.pack_into("<h", data, off, _round_half_up(v[key]))

    redirect_bigmap_floats(data, offsets_ratio_value, y_ratio_value)

    return matches


def redirect_bigmap_floats(data, x_value, y_value):
    """Give the Area Map screen private, scaled copies of the two map-tile-size
    float constants, instead of rewriting the shared originals in place.

    The originals (440.0f / 256.0f in .rdata) are read by the HUD minimap's
    drawing code as well as the Area Map's - rewriting them is what makes the
    minimap render black at high resolutions. See the big note above MAP_OFFSETS.

    Every step is verified against its expected pre-patch bytes; anything
    unexpected raises rather than writing a half-patched exe.
    """
    # 1) the shared constants must still be vanilla (we must NOT have scaled them)
    for off, expect, label in ((SHARED_FLOAT_X, 440.0, "440.0f"), (SHARED_FLOAT_Y, 256.0, "256.0f")):
        (val,) = struct.unpack_from("<f", data, off)
        if val != expect:
            raise RuntimeError(
                f"shared float {label} at 0x{off:X} is {val}, expected vanilla {expect} - refusing to patch"
            )

    # 2) destination slots must be unused (zero) padding
    for axis, slot in PRIVATE_FLOAT_SLOTS.items():
        if data[slot:slot + 4] != b"\x00\x00\x00\x00":
            raise RuntimeError(f"private float slot for {axis} at 0x{slot:X} is not free - refusing to patch")

    # 3) each operand must currently point at the shared constant we expect
    expected_target = {"x": SHARED_FLOAT_X, "y": SHARED_FLOAT_Y}
    for axis, opnds in BIGMAP_FLOAT_OPERANDS.items():
        want = IMAGE_BASE + expected_target[axis]
        for opnd in opnds:
            (cur,) = struct.unpack_from("<I", data, opnd)
            if cur != want:
                raise RuntimeError(
                    f"Area Map {axis} operand at 0x{opnd:X} points to 0x{cur:X}, expected 0x{want:X} - refusing to patch"
                )

    # 4) write the private scaled copies, then repoint every operand at them
    values = {"x": x_value, "y": y_value}
    for axis, slot in PRIVATE_FLOAT_SLOTS.items():
        struct.pack_into("<f", data, slot, values[axis])
        for opnd in BIGMAP_FLOAT_OPERANDS[axis]:
            struct.pack_into("<I", data, opnd, IMAGE_BASE + slot)
        print(
            f"  area-map {axis} float: private copy {values[axis]:.4f} at VA 0x{IMAGE_BASE + slot:X}"
            f" ({len(BIGMAP_FLOAT_OPERANDS[axis])} operands repointed;"
            f" shared original left at vanilla for the HUD minimap)"
        )


# --- Area Map marker-position fix (real code injection - see NOTES.md
# "STARTING POINT FOR NEXT SESSION: Area Map marker bug" for the full
# investigation). This is INCREMENTAL - applied standalone on top of an
# already-patched exe via tools/apply_marker_fix.py, not through patch()
# below (patch()'s match-checks expect vanilla default values, which no
# longer hold once the base resolution/mapscale patch has been applied).
#
# Root cause: the ARE loader bakes vanilla 440x256 pixel space into a
# shared, per-area "Map" calibration object (ctor 0x578C60; obj+0x18/0x1c =
# scale, obj+0x20/0x24 = offset) read by BOTH the HUD's per-frame update and
# the Area Map's own marker-draw call - confirmed via live x32dbg session
# (ECX identical across HUD/menu/Area-Map contexts) AND independently by
# static proof (both paths reach the object through the identical global
# chain [0x7a39fc]->[+8]->call 0x4ae6b0->[+0x218]). One literal shared
# singleton, not two objects that happen to coincide - hence why rescaling
# it in place (tried twice, see redirect_bigmap_floats's sibling note above)
# necessarily broke the HUD minimap both times.
#
# FIX: redirect only the single, genuinely Area-Map-owned call site into the
# transform (VA 0x6946F4, inside function 0x6933A0 - found via
# disasm_helpers.py's authoritative `calls` command; NOT 0x694a39/0x694aac,
# which an earlier session wrongly recorded as this call site - those
# actually call an unrelated note-index getter, 0x5791b0). The other 3
# callers of 0x578E00 (the generic HUD/menu per-frame path) are untouched.
#
# The private object is a byte-for-byte copy of the live shared object, made
# fresh every time this call site executes, with only the two scale fields
# rescaled (scale' = scale / k, k = target/640 or target/480 - offsets are
# left unchanged, per the exact algebra already derived in NOTES.md: scaling
# MapPt_scaled uniformly by k leaves the offset term invariant). The copy
# destination is scratch memory 0x400 bytes below the live stack pointer at
# hook time, NOT a reserved static buffer - every static candidate was
# checked and rejected: .rdata's free tail is read-only at runtime (fine for
# the two rescale-ratio constants below, unusable for a buffer written every
# call), and .data's apparent "free" padding is NOT actually free - its
# bytes are zero only in the static file; at runtime the game writes real
# globals there (confirmed: VA 0x7a39fc, part of the very chain above, sits
# inside that exact byte range), so anything placed there would silently
# corrupt live engine state. Borrowed stack scratch has no such risk: only
# ~0x34 bytes of legitimate stack growth happen between the hook point and
# the call it feeds, so parking 0x28 bytes at esp-0x400 is never touched by
# anything else on this thread.
#
# Every byte below was hand-verified: assembled with keystone, independently
# re-disassembled with capstone, and checked instruction-by-instruction
# against the design before being frozen as a literal constant here.
MARKER_HOOK_VA = 0x6946D3
MARKER_HOOK_DEFAULT = bytes.fromhex("8d54241052")  # lea edx,[esp+0x10]; push edx
MARKER_RESUME_VA = 0x6946D8                         # original next instruction (unchanged)
MARKER_CAVE_VA = 0x73C1D0                           # inside .text's confirmed-free zero tail
MARKER_CAVE_FREE_RUN = (0x33C1D0, 0x33D000)         # file-offset range verified all-zero (3632 bytes)
MARKER_KX_SLOT = 0x38CC08                           # inside .rdata's confirmed-free zero tail,
MARKER_KY_SLOT = 0x38CC0C                           # immediately after the existing PRIVATE_FLOAT_SLOTS use

MARKER_CAVE_BYTES = bytes.fromhex(
    "538d9c2400fcffff575689c689dfb90a000000f3a5d94318d83508cc7800d95b18"
    "d9431cd8350ccc7800d95b1c89d85e5f5b8d54241052e9cc84f5ff"
)
MARKER_HOOK_JMP = bytes.fromhex("e9f87a0a00")  # jmp MARKER_CAVE_VA, from MARKER_HOOK_VA


def add_area_map_marker_fix(data, width, height):
    """Mutates data in place. See the big comment above for the full design.
    Incremental - call this on an already-patched exe's bytes, not a vanilla one.
    """
    hook_off = MARKER_HOOK_VA - IMAGE_BASE
    cave_off = MARKER_CAVE_VA - IMAGE_BASE

    # 1) hook site must still hold the exact vanilla bytes we're replacing
    current = bytes(data[hook_off:hook_off + len(MARKER_HOOK_DEFAULT)])
    if current != MARKER_HOOK_DEFAULT:
        raise RuntimeError(
            f"marker-fix hook at 0x{MARKER_HOOK_VA:X} is {current.hex()}, "
            f"expected {MARKER_HOOK_DEFAULT.hex()} - refusing to patch "
            f"(already patched, or an unexpected exe build)"
        )

    # 2) cave destination and both float slots must be free (zero) padding
    if data[cave_off:cave_off + len(MARKER_CAVE_BYTES)] != b"\x00" * len(MARKER_CAVE_BYTES):
        raise RuntimeError(f"marker-fix cave at 0x{MARKER_CAVE_VA:X} is not free - refusing to patch")
    for slot, label in ((MARKER_KX_SLOT, "kx"), (MARKER_KY_SLOT, "ky")):
        if data[slot:slot + 4] != b"\x00\x00\x00\x00":
            raise RuntimeError(f"marker-fix {label} slot at 0x{slot:X} is not free - refusing to patch")

    # 3) write the two rescale-ratio constants (k = target resolution / vanilla 640x480 GUI canvas)
    kx = width / 640.0
    ky = height / 480.0
    struct.pack_into("<f", data, MARKER_KX_SLOT, kx)
    struct.pack_into("<f", data, MARKER_KY_SLOT, ky)

    # 4) write the cave, then the 5-byte detour jump at the hook site
    data[cave_off:cave_off + len(MARKER_CAVE_BYTES)] = MARKER_CAVE_BYTES
    data[hook_off:hook_off + len(MARKER_HOOK_JMP)] = MARKER_HOOK_JMP

    print(
        f"  area-map marker fix: private calibration object injected\n"
        f"    kx={kx:.6f} at VA 0x{IMAGE_BASE + MARKER_KX_SLOT:X}, "
        f"ky={ky:.6f} at VA 0x{IMAGE_BASE + MARKER_KY_SLOT:X}\n"
        f"    cave: {len(MARKER_CAVE_BYTES)} bytes at VA 0x{MARKER_CAVE_VA:X}\n"
        f"    hook: VA 0x{MARKER_HOOK_VA:X} redirected to the cave "
        f"(other 3 callers of 0x578E00 - the HUD/menu path - untouched)"
    )


########################################################################
# Player/party Area Map marker fix (2026-08-24 follow-up session)
#
# Root cause (see NOTES.md "Player/party marker read site FOUND" for the
# full disassembly trail): player/party marker screen positions are NOT
# recomputed at draw time the way notes are (the fix above handles notes).
# They're computed once/frame by a fully generic dispatcher and cached on
# the party-member struct at +0x28 (X) / +0x34 (Y), still in vanilla
# 640x480 pixel space. The Area Map's own draw function (VA 0x6943D0 -
# correcting an earlier session's false "0x6933A0" nearest-prologue guess,
# the same class of error as the already-documented 0x4B4960 one) reads
# that cache via 0x5791B0 at two call sites - 0x694A39 (party loop) and
# 0x694AAC (player, index 0) - then centers a fixed-size icon on the
# result and draws it. Neither call site touches 0x578E00 or the shared
# calibration object at all, so this fix cannot regress the HUD/menu path
# the way the earlier calibration-object attempts did - it only touches
# code reached from inside the Area Map's own draw function.
#
# FIX: rescale the X/Y that 0x5791B0 returns, in the caller, immediately
# after the call succeeds and before the existing icon-centering subtract.
# Reuses the kx/ky float constants add_area_map_marker_fix() already wrote
# to MARKER_KX_SLOT/MARKER_KY_SLOT - no new constants needed. Both hooks
# reorder the reproduced original instructions so the flag/branch each one
# depends on (test ecx,ecx for the party loop's next `je`; test eax,eax for
# the player call's success check) is computed fresh, immediately before
# the branch that consumes it - the x87 fild/fmul/fistp sequence used for
# the rescale doesn't touch integer EFLAGS, but relying on that for an
# instruction whose flag outputs are otherwise documented "undefined"
# (e.g. a 3-operand imul) would be fragile, so this design avoids the
# question entirely rather than depending on undefined behavior.
#
# Every byte below was assembled with keystone, independently re-verified
# with capstone against this exact design, before being frozen as a
# literal constant here (see the interactive session transcript, not
# reproduced in-repo).
PARTY_HOOK_VA = 0x694A42
PARTY_HOOK_DEFAULT = bytes.fromhex("8b4b6485c9")  # mov ecx,[ebx+0x64]; test ecx,ecx
PARTY_RESUME_VA = 0x694A47                          # original next instruction (je 0x694a81, unchanged)
PARTY_CAVE_VA = 0x73C20C                            # immediately after add_area_map_marker_fix()'s own cave
PARTY_CAVE_BYTES = bytes.fromhex(
    "db442414d80d08cc7800db5c2414db442418d80d0ccc7800db5c24188b4b6485c9e91588f5ff"
)
PARTY_HOOK_JMP = bytes.fromhex("e9c5770a00")  # jmp PARTY_CAVE_VA, from PARTY_HOOK_VA

PLAYER_HOOK_VA = 0x694AB1
# test eax,eax; je 0x694b1b; mov ecx,[esp+0x18]; mov eax,[esp+0x14] - taken as one
# 12-byte block (5 alone would land mid-instruction); only 5 become the jmp, the
# other 7 are dead NOP padding purely for readability in a debugger.
PLAYER_HOOK_DEFAULT = bytes.fromhex("85c074668b4c24188b442414")
PLAYER_RESUME_VA = 0x694ABD                         # original next instruction (push 0x3f800000, unchanged)
PLAYER_FAIL_VA = 0x694B1B                           # original je target on failure, unchanged
PLAYER_CAVE_VA = 0x73C232                           # immediately after PARTY_CAVE_BYTES
PLAYER_CAVE_BYTES = bytes.fromhex(
    "85c00f84e188f5ffdb442414d80d08cc7800db5c2414db442418d80d0ccc7800db5c24188b4c"
    "24188b442414e95a88f5ff"
)
PLAYER_HOOK_JMP = bytes.fromhex("e97c770a00")  # jmp PLAYER_CAVE_VA, from PLAYER_HOOK_VA
PLAYER_HOOK_NOP_PAD = b"\x90" * (len(PLAYER_HOOK_DEFAULT) - len(PLAYER_HOOK_JMP))


def add_party_player_marker_fix(data):
    """Mutates data in place. Incremental - requires add_area_map_marker_fix()
    to already be applied (reuses its MARKER_KX_SLOT/MARKER_KY_SLOT values).
    See the big comment above for the full design.
    """
    for slot, label in ((MARKER_KX_SLOT, "kx"), (MARKER_KY_SLOT, "ky")):
        if data[slot:slot + 4] == b"\x00\x00\x00\x00":
            raise RuntimeError(
                f"{label} slot at 0x{slot:X} is zero - add_area_map_marker_fix() "
                f"must be applied first, this fix reuses its constants"
            )

    checks = (
        (PARTY_HOOK_VA, PARTY_HOOK_DEFAULT, "party hook"),
        (PLAYER_HOOK_VA, PLAYER_HOOK_DEFAULT, "player hook"),
    )
    for va, expected, label in checks:
        off = va - IMAGE_BASE
        current = bytes(data[off:off + len(expected)])
        if current != expected:
            raise RuntimeError(
                f"{label} at 0x{va:X} is {current.hex()}, expected {expected.hex()} "
                f"- refusing to patch (already patched, or an unexpected exe build)"
            )

    cave_off = PARTY_CAVE_VA - IMAGE_BASE
    cave_len = len(PARTY_CAVE_BYTES) + len(PLAYER_CAVE_BYTES)
    if data[cave_off:cave_off + cave_len] != b"\x00" * cave_len:
        raise RuntimeError(f"party/player marker-fix cave at 0x{PARTY_CAVE_VA:X} is not free - refusing to patch")

    party_cave_off = PARTY_CAVE_VA - IMAGE_BASE
    player_cave_off = PLAYER_CAVE_VA - IMAGE_BASE
    data[party_cave_off:party_cave_off + len(PARTY_CAVE_BYTES)] = PARTY_CAVE_BYTES
    data[player_cave_off:player_cave_off + len(PLAYER_CAVE_BYTES)] = PLAYER_CAVE_BYTES

    party_hook_off = PARTY_HOOK_VA - IMAGE_BASE
    data[party_hook_off:party_hook_off + len(PARTY_HOOK_JMP)] = PARTY_HOOK_JMP

    player_hook_off = PLAYER_HOOK_VA - IMAGE_BASE
    data[player_hook_off:player_hook_off + len(PLAYER_HOOK_JMP)] = PLAYER_HOOK_JMP
    pad_start = player_hook_off + len(PLAYER_HOOK_JMP)
    data[pad_start:pad_start + len(PLAYER_HOOK_NOP_PAD)] = PLAYER_HOOK_NOP_PAD

    print(
        f"  player/party marker fix: draw-time rescale injected\n"
        f"    party cave: {len(PARTY_CAVE_BYTES)} bytes at VA 0x{PARTY_CAVE_VA:X}, "
        f"hook VA 0x{PARTY_HOOK_VA:X}\n"
        f"    player cave: {len(PLAYER_CAVE_BYTES)} bytes at VA 0x{PLAYER_CAVE_VA:X}, "
        f"hook VA 0x{PLAYER_HOOK_VA:X}\n"
        f"    reused kx/ky from MARKER_KX_SLOT/MARKER_KY_SLOT "
        f"(0x{MARKER_KX_SLOT:X}/0x{MARKER_KY_SLOT:X})"
    )


def find_matches(data):
    """Return {offset_key: [offsets whose current value == known default]}."""
    matches = {k: [] for k in OFFSETS}
    for key, offsets in OFFSETS.items():
        default = DEFAULTS[key]
        for off in offsets:
            if off + 2 > len(data):
                continue  # offset belongs to a different exe build (e.g. macOS), out of range here
            (val,) = struct.unpack_from("<h", data, off)  # signed 16-bit LE
            if val == default:
                matches[key].append(off)
    return matches


def find_dialog_letterbox(data):
    found = []
    for off, default in DIALOG_LETTERBOX_OFFSETS.items():
        (val,) = struct.unpack_from("<L", data, off)
        if val == default:
            found.append(off)
    return found


def patch(exe_path, width, height, letterbox=False, mapscale=False, backup_suffix=".hires-backup"):
    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    matches = find_matches(data)
    for key, offs in matches.items():
        print(f"  {key}: {len(offs)} match(es) at {[hex(o) for o in offs]}")

    ok = (
        len(matches["negative_offsets_x"]) >= 1
        and len(matches["negative_offsets_y"]) >= 1
        and len(matches["positive_offsets_x"]) >= 1
        and len(matches["positive_offsets_y"]) >= 1
    )
    if not ok:
        print("\nERROR: did not find enough known-default offsets to trust this exe build. "
              "No changes made.")
        return False

    dialog_offs = find_dialog_letterbox(data) if letterbox else []
    if letterbox and not dialog_offs:
        print("\nWARNING: letterbox requested but no matching dialog-letterbox offset found "
              "(gog-only in this port) - skipping that part, proceeding with the rest.")

    print("\npre-hires-patch backup:")
    backup_path = backup_paths.make_backup(exe_path, backup_suffix)

    for off in matches["negative_offsets_x"]:
        struct.pack_into("<h", data, off, -width)
    for off in matches["negative_offsets_y"]:
        struct.pack_into("<h", data, off, -height)
    for off in matches["positive_offsets_x"]:
        struct.pack_into("<h", data, off, width)
    for off in matches["positive_offsets_y"]:
        struct.pack_into("<h", data, off, height)

    if letterbox and dialog_offs:
        letterbox_factor = (1.0 / ((width / height) * 1.75))  # gog formula
        for off in dialog_offs:
            struct.pack_into("<f", data, off, letterbox_factor)
        print(f"  wrote dialog letterbox factor {letterbox_factor} at {[hex(o) for o in dialog_offs]}")

    if mapscale:
        print("\napplying map-screen scale patch...")
        map_matches = find_map_matches(data)
        for key, offs in map_matches.items():
            print(f"  {key}: {len(offs)} match(es) at {[hex(o) for o in offs]}")
        patch_map_scale(data, width, height)

    with open(exe_path, "wb") as f:
        f.write(data)

    print(f"\npatched {exe_path} for {width}x{height} (letterbox={letterbox}, mapscale={mapscale})")
    return True


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5, 6):
        print(f"usage: {sys.argv[0]} WIDTH HEIGHT EXE [letterbox=yes|no] [mapscale=yes|no]")
        sys.exit(1)
    w, h, exe = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    lbox = len(sys.argv) >= 5 and sys.argv[4].lower() in ("yes", "true", "1")
    mscale = len(sys.argv) == 6 and sys.argv[5].lower() in ("yes", "true", "1")
    success = patch(exe, w, h, lbox, mscale)
    sys.exit(0 if success else 1)
