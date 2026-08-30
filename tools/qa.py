"""Phase 3: automated QA. One command, one report. See docs/PHASE3_SPEC.md.

    python tools/qa.py                          # human report, exit 0/1
    python tools/qa.py --json out/qa_report.json

Two independent blocks, both offline (no game needed, real install never
touched):

  A. Per-resolution checks across all 49 k1hrm 1.5 sets. Each test binary is
     built by the same officially-supported chain
     `tools/verify_official_chain.py` uses (official UniWS artifact -> official
     k1hrm at W x H -> our layer via `patcher/k1amf/steps.apply_all`), then
     re-verified from a fresh read with `patcher/k1amf/verify.check` - the same
     19-check battery the shipped patcher runs on every install - plus the
     Override/map.gui box check from `patcher/k1amf/detect.check_map_gui`.

  B. The note-table's position-key scheme, proven collision-free across every
     map note in the game (`tools/note_corrections.build/validate`, which
     builds its uniqueness table from ALL notes, not just the corrected ones),
     and the shipped frozen table proven to match a fresh derivation
     (`tools/freeze_note_table`).

Nothing here is new patching logic - it wires up tools this project already
built and trusts.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
PATCHER = os.path.join(ROOT, "patcher")
for _p in (TOOLS, PATCHER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import note_table_patch as ntp  # noqa: E402

from k1amf import detect as kdetect  # noqa: E402
from k1amf import steps as ksteps  # noqa: E402
from k1amf import verify as kverify  # noqa: E402
from k1amf.detect import Refusal  # noqa: E402
from k1amf.steps import PatchError  # noqa: E402

UNIWS_BASE = os.path.join(ROOT, "backups", "swkotor.exe.uniws-only-backup")
KHRM_ROOT = os.path.join(ROOT, "downloads", "k1hrm-1.5")
KHRM_PL = os.path.join(KHRM_ROOT, "hires_patcher.pl")
WORK = os.path.join(ROOT, "staging", "qa")

# Matches the live, in-game-confirmed exe (STATE.md: letterbox-on has never
# been run in game - that gap is Phase 4's, not Phase 3's).
LETTERBOX = "no"


def discover_resolutions():
    """[(width, height, gui_set_dir), ...] for every k1hrm 1.5 set on disk.

    Enumerated, not hardcoded, so a different k1hrm drop is picked up as-is.
    """
    out = []
    for aspect in sorted(os.listdir(KHRM_ROOT)):
        aspect_dir = os.path.join(KHRM_ROOT, aspect)
        if not os.path.isdir(aspect_dir):
            continue
        for name in sorted(os.listdir(aspect_dir)):
            if not name.startswith("gui."):
                continue
            w, h = name[len("gui."):].split("x")
            out.append((int(w), int(h), os.path.join(aspect_dir, name)))
    out.sort()
    return out


def build_official_base(width, height, letterbox=LETTERBOX):
    """Official k1hrm applied to the official UniWS artifact. Returns bytes.

    Needs a real file on disk (external perl tool); the temp copy is removed
    before returning, so nothing accumulates under staging/.

    `letterbox` is a parameter only so tools/build_test_install.py can build the
    letterbox-on configuration Phase 4 has to test; this QA sweep always runs
    the default, matching the in-game-confirmed exe.
    """
    tmp_dir = tempfile.mkdtemp(dir=WORK)
    try:
        exe = os.path.join(tmp_dir, "swkotor.exe")
        shutil.copyfile(UNIWS_BASE, exe)
        r = subprocess.run(
            ["perl", KHRM_PL, str(width), str(height), letterbox, "swkotor.exe"],
            cwd=tmp_dir, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                "official k1hrm failed for %dx%d:\n%s\n%s"
                % (width, height, r.stdout, r.stderr))
        with open(exe, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def check_map_gui_box(gui_set_dir, width, height):
    """(ok, label) for the Override/map.gui box, using this set's own file -
    not the live install's - via the same detect.check_map_gui the patcher
    itself gates on."""
    scratch = tempfile.mkdtemp(dir=WORK)
    try:
        override = os.path.join(scratch, "Override")
        os.makedirs(override)
        shutil.copyfile(os.path.join(gui_set_dir, "map.gui"),
                        os.path.join(override, "map.gui"))
        try:
            got = kdetect.check_map_gui(scratch, width, height)
        except Refusal as e:
            return False, "Override/map.gui LBL_Map box: %s" % e
        want = kdetect.expected_map_extent(width, height)
        return True, ("Override/map.gui LBL_Map box is %s (formula: %s, "
                      "tolerance %dpx)" % (got, want, kdetect.GUI_TOLERANCE))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def check_resolution(width, height, gui_set_dir, table):
    """One resolution's full result: {width, height, checks, pass, error,
    bytes_changed}."""
    result = {"width": width, "height": height, "checks": [], "pass": False,
              "error": None, "bytes_changed": None}
    try:
        before = build_official_base(width, height)
    except RuntimeError as e:
        result["error"] = str(e)
        return result

    data = bytearray(before)
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            ksteps.apply_all(data, width, height, table)
    except PatchError as e:
        result["error"] = "our layer refused: %s\n%s" % (e, log.getvalue())
        return result

    before_arr = np.frombuffer(before, dtype=np.uint8)
    after_arr = np.frombuffer(data, dtype=np.uint8)
    n = min(before_arr.size, after_arr.size)
    result["bytes_changed"] = int(np.count_nonzero(
        before_arr[:n] != after_arr[:n])) + abs(before_arr.size - after_arr.size)

    code_va, table_va = ntp.layout(data, len(table))
    checks = kverify.check(before, data, width, height, table, code_va, table_va)

    ok_gui, label_gui = check_map_gui_box(gui_set_dir, width, height)
    checks.append((ok_gui, label_gui))

    # Explicit int16-range assertion (spec item A.4): apply_all/struct.pack_into
    # would already have raised on overflow, but make it a visible, named check
    # rather than an implicit property of the write succeeding.
    range_ok = True
    for _key, off, tpl, _default in kdetect.scale_sites():
        (val,) = struct.unpack_from(tpl, data, off)
        range_ok &= -32768 <= val <= 32767
    checks.append((range_ok, "every map-scale int16 write is in signed 16-bit range"))

    # The stale-k1hrm input (F25). `build_official_base` uses hires_patcher.PL,
    # which writes the four Area Map centring constants correctly - so the
    # broken input a real Windows user gets from hires_patcher.EXE never occurs
    # above, and this suite could not otherwise see it. Roll those four back to
    # vanilla and require the pipeline to converge on byte-identical output.
    stale = bytearray(before)
    for offs, value in ((kdetect.CENTRING_X, kdetect.VANILLA_W),
                        (kdetect.CENTRING_Y, kdetect.VANILLA_H)):
        for off in offs:
            struct.pack_into("<h", stale, off, value)
    converged = kdetect.centring_state(stale, width, height) == "stale"
    if converged:
        try:
            with contextlib.redirect_stdout(log):
                ksteps.apply_all(stale, width, height, table)
            converged = bytes(stale) == bytes(data)
        except PatchError:
            converged = False
    checks.append((converged, "a k1hrm exe left stale by hires_patcher.exe is "
                              "detected and converges on the same bytes"))

    result["checks"] = checks
    result["pass"] = all(ok for ok, _ in checks)
    return result


def check_note_table():
    """The note-table position-key scheme, proven against every note in the
    game, plus the shipped frozen table proven to match a fresh derivation."""
    import freeze_note_table
    import note_corrections

    corrections, skipped, awaiting, all_keys, stale = note_corrections.build()
    problems = note_corrections.validate(corrections, all_keys)
    multi_owner = [k for k, owners in all_keys.items() if len(owners) > 1]

    frozen, fmeta = freeze_note_table.load_frozen()
    fresh_table, fresh_meta = freeze_note_table.build()
    frozen_present = frozen is not None
    frozen_matches = frozen_present and frozen == fresh_table

    ok = (not problems) and not multi_owner and frozen_matches

    return {
        "pass": ok,
        "corrections": len(corrections),
        "rejected": len(skipped),
        "awaiting_review": len(awaiting),
        "stale_decisions": len(stale),
        "total_note_keys": len(all_keys),
        "keys_with_multiple_owners": len(multi_owner),
        "validation_problems": problems,
        "frozen_table_present": frozen_present,
        "frozen_table_entries": fmeta["entries"] if fmeta else None,
        "frozen_table_sha256": fmeta["sha256"] if fmeta else None,
        "frozen_table_matches_fresh_derivation": frozen_matches,
        "fresh_entries": fresh_meta["entries"],
    }


def run():
    os.makedirs(WORK, exist_ok=True)
    for need in (UNIWS_BASE, KHRM_PL):
        if not os.path.isfile(need):
            raise SystemExit("missing prerequisite: %s" % need)

    table, meta = ksteps.load_note_table()
    resolutions = discover_resolutions()

    per_resolution = []
    for width, height, gui_set_dir in resolutions:
        per_resolution.append(check_resolution(width, height, gui_set_dir, table))

    note_table = check_note_table()

    overall_pass = note_table["pass"] and all(r["pass"] for r in per_resolution)
    report = {
        "letterbox": LETTERBOX,
        "note_table_entries": meta["entries"],
        "resolutions_tested": len(resolutions),
        "per_resolution": per_resolution,
        "note_table": note_table,
        "pass": overall_pass,
    }
    return report


def print_report(report):
    print("K1 Area Map Fixes - Phase 3 automated QA")
    print("=" * 72)
    print("k1hrm letterbox: %s  (letterbox-on is Phase 4's job, per RELEASE_PLAN.md 2.9)"
          % report["letterbox"])
    print("note table:      %d entries" % report["note_table_entries"])
    print()
    print("A. Per-resolution checks (%d k1hrm 1.5 sets)" % report["resolutions_tested"])
    print("-" * 72)
    fails = [r for r in report["per_resolution"] if not r["pass"]]
    for r in report["per_resolution"]:
        mark = "PASS" if r["pass"] else "FAIL"
        extra = ""
        if r["error"]:
            extra = "  ERROR: %s" % r["error"]
        elif not r["pass"]:
            bad = [label for ok, label in r["checks"] if not ok]
            extra = "  failing: " + "; ".join(bad)
        print("  [%s] %5dx%-5d  (%s bytes changed)%s"
              % (mark, r["width"], r["height"], r["bytes_changed"], extra))
    print("  %d/%d resolutions pass" % (len(report["per_resolution"]) - len(fails),
                                        len(report["per_resolution"])))

    print()
    print("B. Note-table position-key scheme")
    print("-" * 72)
    nt = report["note_table"]
    print("  reviewed corrections:            %d" % nt["corrections"])
    print("  rejected by review:               %d" % nt["rejected"])
    print("  awaiting review:                  %d" % nt["awaiting_review"])
    print("  stale decision rows:              %d" % nt["stale_decisions"])
    print("  total note keys across the game:  %d" % nt["total_note_keys"])
    print("  keys shared by >1 note:           %d  (must be 0)"
          % nt["keys_with_multiple_owners"])
    print("  frozen table present:              %s" % nt["frozen_table_present"])
    print("  frozen table entries:              %s" % nt["frozen_table_entries"])
    print("  frozen table matches fresh derive: %s"
          % nt["frozen_table_matches_fresh_derivation"])
    if nt["validation_problems"]:
        print("  PROBLEMS:")
        for p in nt["validation_problems"][:20]:
            print("    " + p)
    print("  %s" % ("PASS" if nt["pass"] else "FAIL"))

    print()
    print("=" * 72)
    print("OVERALL: %s" % ("PASS" if report["pass"] else "FAIL"))


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", metavar="PATH")
    args = parser.parse_args(argv)

    report = run()
    print_report(report)

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print("\nwrote %s" % args.json)

    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
