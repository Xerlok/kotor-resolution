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
    """A layer refused. The exe on disk has not been touched."""


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
        raise PatchError("the map-note table is missing from the patcher: %s" % e)
    if hashlib.sha256(table).hexdigest() != meta.get("sha256") or \
            len(table) != meta.get("bytes"):
        raise PatchError(
            "the map-note table in this patcher does not match its own "
            "checksum - the download is damaged. Re-download rather than "
            "patching with it.")
    if len(table) % ntp.ENTRY_BYTES:
        raise PatchError("the map-note table is not a whole number of entries")
    return table, meta


def apply_all(data, width, height, table):
    """Run every layer against `data` in place. Returns what was done, for the
    manifest. Raises PatchError before writing anything if a layer refuses.

    `data` is a scratch copy: the caller writes it to disk only if this returns.
    """
    steps = []

    # 1. mapscale + the private float copies that keep the HUD minimap alive.
    try:
        matches = hires_patch.patch_map_scale(data, width, height)
    except RuntimeError as e:
        raise PatchError(str(e))
    n_sites = sum(len(v) for v in matches.values())
    if n_sites != detect.SCALE_SITE_COUNT:
        raise PatchError(
            "%d map-scale constants held their expected values, not the %d this "
            "exe should have - it is not the build this patcher knows, or "
            "something else has edited it. Nothing was written."
            % (n_sites, detect.SCALE_SITE_COUNT))
    steps.append({"step": "map scale", "sites": n_sites,
                  "private_floats": {k: hex(hires_patch.IMAGE_BASE + v)
                                     for k, v in hires_patch.PRIVATE_FLOAT_SLOTS.items()}})

    # 2. + 3. the three marker caves.
    try:
        hires_patch.add_area_map_marker_fix(data, width, height)
        hires_patch.add_party_player_marker_fix(data)
    except RuntimeError as e:
        raise PatchError(str(e))
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
        raise PatchError(str(e))
    steps.append({"step": "reserve table space",
                  "region": hex(pe_space.IMAGE_BASE + region_rva),
                  "bytes": len(data) - before, "already_present": not grew})

    # 5. the note table itself, plus the match routine and its hook.
    code_va, table_va = ntp.layout(data, len(table))
    code = ntp.build_code(table_va, table_va + len(table), ntp.RESUME_VA, code_va)
    problems = ntp.verify_code(code, code_va, table_va, table_va + len(table),
                               ntp.RESUME_VA, quiet=True)
    if problems:
        raise PatchError("the map-note match routine failed its own "
                         "verification:\n  " + "\n  ".join(problems))

    hook_off = ntp.HOOK_VA - hires_patch.IMAGE_BASE
    if bytes(data[hook_off:hook_off + 5]) != ntp.HOOK_DEFAULT:
        raise PatchError("the map-note hook site at 0x%X does not hold the "
                         "expected original bytes" % ntp.HOOK_VA)
    code_off = ntp.va_to_off(data, code_va)
    table_off = ntp.va_to_off(data, table_va)
    for label, off, length in (("match routine", code_off, len(code)),
                               ("note table", table_off, len(table))):
        if set(data[off:off + length]) != {0}:
            raise PatchError("the destination for the %s is not free - "
                             "refusing to overwrite it" % label)

    data[code_off:code_off + len(code)] = code
    data[table_off:table_off + len(table)] = table
    data[hook_off:hook_off + 5] = b"\xe9" + struct.pack(
        "<i", code_va - (ntp.HOOK_VA + 5))
    steps.append({"step": "map-note corrections",
                  "entries": len(table) // ntp.ENTRY_BYTES,
                  "routine": hex(code_va), "table": hex(table_va),
                  "hook": hex(ntp.HOOK_VA)})
    return steps
