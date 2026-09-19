"""The five patch layers, applied to one in-memory image.

Order matters and is not ours to choose: it is the order
`tools/verify_official_chain.py` uses, which is the order that reproduced the
live, in-game-confirmed exe byte for byte. Anything that reorders these must
re-run `patcher/selftest.py` and show the same md5.

Every layer is the same function the development tools call - see
`_toolpath.py` for why nothing is copied here - except the note table, which
ships frozen (`data/note_table.bin`) rather than re-derived from the player's
own module files.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct

from . import _toolpath  # noqa: F401
from . import detect

import hires_patch
import note_table_patch as ntp
import pe_space

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data")


class PatchError(Exception):
    """A layer refused. The exe on disk has not been touched.

    `log_detail`, when set, is a hex dump of the bytes that made a layer
    refuse - too long and too technical for the default screen message, but
    exactly what identifies which other tool wrote them. install.py logs it
    unconditionally (`out.detail`), same as everything else that only
    belongs in last-run-log.txt.
    """

    def __init__(self, message, log_detail=None):
        super().__init__(message)
        self.log_detail = log_detail


def _file_state_error(what, technical, hint=None, dump=None):
    """A PatchError for 'this part of the exe isn't what we expected'.

    `what` says in plain words what step was being attempted. `technical`
    is the raw message from the tools/ layer (addresses, hex bytes) - kept
    at the end, labelled, rather than dropped: it is what a bug report or a
    second look at COMPATIBILITY.txt needs, even though a first-time modder
    does not. `dump`, if given, is a hex dump of the bytes actually found -
    see PatchError.log_detail.
    """
    lines = [
        what,
        "",
        "This patcher checks the exact bytes it's about to change before it",
        "writes anything, and what's there now isn't what it expects. Your",
        "game file has not been touched.",
        "",
        "The usual reasons, most likely first:",
        "  - this patch is already installed",
        "  - another mod has changed this part of swkotor.exe - see",
        "    COMPATIBILITY.txt for mods known to conflict with this one",
        "  - this isn't the exact game build this patcher supports",
    ]
    if hint:
        lines += ["", hint]
    lines += ["", "(technical detail: %s)" % technical]
    log_detail = ("Bytes actually found, where known values were expected:\n%s"
                  % dump) if dump else None
    return PatchError("\n".join(lines), log_detail=log_detail)


def load_note_table():
    """(table_bytes, metadata) as reviewed and frozen by tools/freeze_note_table.py."""
    bin_path = os.path.join(DATA, "note_table.bin")
    meta_path = os.path.join(DATA, "note_table.json")
    try:
        with open(bin_path, "rb") as fh:
            table = fh.read()
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    except OSError as e:
        raise PatchError(
            "Couldn't read the map data that ships with this patcher (%s).\n"
            "\n"
            "Your download is probably incomplete or was unzipped\n"
            "incorrectly. Unzip it again, or download it fresh." % e)
    if hashlib.sha256(table).hexdigest() != meta.get("sha256") or \
            len(table) != meta.get("bytes"):
        raise PatchError(
            "This download is damaged.\n"
            "\n"
            "The map data that came with the patcher doesn't match its own\n"
            "checksum, so something went wrong downloading or unzipping it.\n"
            "Download it again.")
    if len(table) % ntp.ENTRY_BYTES:
        raise PatchError(
            "The map data that ships with this patcher looks damaged (its\n"
            "size is wrong). Unzip the download again, or download it fresh.")
    return table, meta


def apply_all(data, width, height, table):
    """Run every layer against `data` in place. Returns what was done, for the
    manifest. Raises PatchError before writing anything if a layer refuses.

    `data` is a scratch copy: the caller writes it to disk only if this returns.
    """
    steps = []

    # 0. finish k1hrm's job if its shipped .exe left it half-done.
    #
    # Not our layer and not our bug: these four int16s belong to k1hrm, and
    # hires_patcher.PL writes them correctly. Its compiled hires_patcher.EXE -
    # the one k1hrm's own .bat and README tell Windows users to run - does not,
    # and the Area Map is then drawn ((W-640)/2, (H-480)/2) off its box. We fix
    # it rather than refuse because the alternative we could honestly offer the
    # player is "install Perl, or hex-edit four offsets k1hrm never documented".
    # detect.check_centring has already refused anything that is neither correct
    # nor exactly vanilla, so this only ever turns 640/480 into width/height.
    centring = detect.check_centring(data, width, height)
    if centring == "stale":
        for offs, value in ((detect.CENTRING_X, width), (detect.CENTRING_Y, height)):
            for off in offs:
                struct.pack_into("<h", data, off, value)
        steps.append({"step": "k1hrm Area Map centring constants",
                      "sites": [hex(o) for o in detect.CENTRING_X + detect.CENTRING_Y],
                      "from": [detect.VANILLA_W, detect.VANILLA_H],
                      "to": [width, height],
                      "why": "hires_patcher.exe leaves these vanilla; the .pl does not"})

    # 1. mapscale + the private float copies that keep the HUD minimap alive.
    try:
        matches = hires_patch.patch_map_scale(data, width, height)
    except RuntimeError as e:
        raise _file_state_error(
            "Couldn't set the Area Map's zoom level for this resolution.",
            str(e), dump=hires_patch.describe_map_scale_state(data))
    n_sites = sum(len(v) for v in matches.values())
    if n_sites != detect.SCALE_SITE_COUNT:
        raise _file_state_error(
            "Couldn't set the Area Map's zoom level for this resolution.",
            "%d map-scale constants held their expected values, not the %d "
            "this exe should have" % (n_sites, detect.SCALE_SITE_COUNT),
            dump=hires_patch.describe_map_scale_state(data))
    steps.append({"step": "map scale", "sites": n_sites,
                  "private_floats": {k: hex(hires_patch.IMAGE_BASE + v)
                                     for k, v in hires_patch.PRIVATE_FLOAT_SLOTS.items()}})

    # 1b. scale the Area Map marker icons - notes, player arrow and party -
    # so they stay usable as the map box grows. All by the same factor, so
    # their vanilla size relationship is preserved (the player arrow stays the
    # biggest). No-ops (writes nothing) at 2560x1600 and below, which is why
    # the confirmed exe is still reproduced byte for byte.
    try:
        icon_scale, icon_sites = hires_patch.patch_note_icons(data, width, height)
    except RuntimeError as e:
        raise _file_state_error(
            "Couldn't resize the map markers (notes, player arrow, party "
            "members) for this resolution.",
            str(e), dump=hires_patch.describe_note_icons_state(data))
    if icon_sites:
        steps.append({"step": "map marker icon scale", "scale": icon_scale,
                      "sites": icon_sites,
                      "note": "note, player-arrow and party markers, all x%d"
                              % icon_scale})

    # 2. + 3. the three marker caves.
    try:
        hires_patch.add_area_map_marker_fix(data, width, height)
        hires_patch.add_party_player_marker_fix(data)
    except RuntimeError as e:
        raise _file_state_error(
            "Couldn't fix where the player, party and map-note markers are "
            "drawn on the Area Map.",
            str(e),
            hint="If you have KMRP (KOTOR Modern Restoration Patch) applied "
                 "to this exe: that mod and this one write to the same "
                 "spot and cannot be used together. See COMPATIBILITY.txt.",
            dump=hires_patch.describe_marker_fix_state(data))
    steps.append({"step": "map-note marker calibration",
                  "cave": hex(hires_patch.MARKER_CAVE_VA),
                  "hook": hex(hires_patch.MARKER_HOOK_VA)})
    steps.append({"step": "party marker", "cave": hex(hires_patch.PARTY_CAVE_VA),
                  "hook": hex(hires_patch.PARTY_HOOK_VA)})
    steps.append({"step": "player marker", "cave": hex(hires_patch.PLAYER_CAVE_VA),
                  "hook": hex(hires_patch.PLAYER_HOOK_VA)})

    # 4. room for the note table at the end of .rsrc (grows the file by 8 KB).
    before = len(data)
    try:
        region_rva, grew = pe_space.extend(data)
    except ValueError as e:
        raise _file_state_error(
            "Couldn't make room in the file for the corrected map-note "
            "positions.",
            str(e), dump=pe_space.describe_sections(data))
    steps.append({"step": "reserve table space",
                  "region": hex(pe_space.IMAGE_BASE + region_rva),
                  "bytes": len(data) - before, "already_present": not grew})

    # 5. the note table itself, plus the match routine and its hook.
    code_va, table_va = ntp.layout(data, len(table))
    code = ntp.build_code(table_va, table_va + len(table), ntp.RESUME_VA, code_va)
    problems = ntp.verify_code(code, code_va, table_va, table_va + len(table),
                               ntp.RESUME_VA, quiet=True)
    if problems:
        raise PatchError(
            "Hit an internal problem preparing the map-note correction "
            "code - not something about your game file. Your game has not "
            "been changed.\n"
            "\n"
            "This shouldn't happen. Please report it and attach "
            "last-run-log.txt from this folder.\n"
            "\n"
            "(technical detail: " + "; ".join(problems) + ")")

    hook_off = ntp.HOOK_VA - hires_patch.IMAGE_BASE
    if bytes(data[hook_off:hook_off + 5]) != ntp.HOOK_DEFAULT:
        raise _file_state_error(
            "Couldn't set up the map-note position correction.",
            "the map-note hook site at 0x%X does not hold the expected "
            "original bytes" % ntp.HOOK_VA,
            dump=hires_patch.dump_bytes(
                data, [(hook_off, 5, ntp.HOOK_VA, "map-note hook")]))
    code_off = ntp.va_to_off(data, code_va)
    table_off = ntp.va_to_off(data, table_va)
    for label, off, length in (("match routine", code_off, len(code)),
                               ("note table", table_off, len(table))):
        if set(data[off:off + length]) != {0}:
            raise _file_state_error(
                "Couldn't set up the map-note position correction.",
                "the destination for the %s is not free" % label,
                dump=hires_patch.dump_bytes(
                    data, [(off, min(length, 256), code_va if label == "match routine" else table_va,
                            label + " (truncated to 256 bytes)" if length > 256 else label)]))

    data[code_off:code_off + len(code)] = code
    data[table_off:table_off + len(table)] = table
    data[hook_off:hook_off + 5] = b"\xe9" + struct.pack(
        "<i", code_va - (ntp.HOOK_VA + 5))
    steps.append({"step": "map-note corrections",
                  "entries": len(table) // ntp.ENTRY_BYTES,
                  "routine": hex(code_va), "table": hex(table_va),
                  "hook": hex(ntp.HOOK_VA)})
    return steps
