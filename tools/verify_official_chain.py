"""Rebuild the officially-supported install chain and prove our layer applies to it.

    python tools/verify_official_chain.py [WIDTH HEIGHT] [--letterbox yes|no]

Chain:  official-UniWS artifact
          -> official k1hrm (downloads/k1hrm-1.5/hires_patcher.pl, needs perl)
          -> patch_map_scale (+ private float redirect)
          -> apply_marker_fix / apply_party_player_marker_fix
          -> pe_space + note_table_patch

It also patches a second copy with our own port of k1hrm and diffs the two, which
is what established (2026-08-30) that the port is byte-identical to the official
patcher. See docs/RELEASE_PLAN.md section 2.9.

Everything is written under staging/; the real install is never touched.
"""
import hashlib
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hires_patch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIWS_BASE = os.path.join(ROOT, "backups", "swkotor.exe.uniws-only-backup")
KHRM_PL = os.path.join(ROOT, "downloads", "k1hrm-1.5", "hires_patcher.pl")
WORK = os.path.join(ROOT, "staging", "verify-chain")
LIVE = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor\swkotor.exe"


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def diff_runs(a_path, b_path):
    """Contiguous differing regions between two files, as (start, end) pairs."""
    a, b = np.fromfile(a_path, dtype=np.uint8), np.fromfile(b_path, dtype=np.uint8)
    n = min(a.size, b.size)
    d = np.flatnonzero(a[:n] != b[:n])
    if d.size == 0:
        return [], a.size != b.size
    brk = np.flatnonzero(np.diff(d) > 8)
    starts = np.concatenate(([d[0]], d[brk + 1]))
    ends = np.concatenate((d[brk], [d[-1]]))
    return [(int(s), int(e)) for s, e in zip(starts, ends)], a.size != b.size


def main(argv):
    width = int(argv[0]) if len(argv) > 0 and argv[0].isdigit() else 2560
    height = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 1600
    letterbox = "no"
    if "--letterbox" in argv:
        letterbox = argv[argv.index("--letterbox") + 1]

    for need in (UNIWS_BASE, KHRM_PL):
        if not os.path.isfile(need):
            raise SystemExit(f"missing prerequisite: {need}")

    os.makedirs(WORK, exist_ok=True)
    print(f"target {width}x{height}, k1hrm letterbox={letterbox}")
    print(f"base   {os.path.relpath(UNIWS_BASE, ROOT)}  md5 {md5(UNIWS_BASE)}")

    # --- 1. official k1hrm -------------------------------------------------
    official_dir = os.path.join(WORK, "official")
    os.makedirs(official_dir, exist_ok=True)
    official = os.path.join(official_dir, "swkotor.exe")
    shutil.copyfile(UNIWS_BASE, official)
    run(["perl", KHRM_PL, str(width), str(height), letterbox, "swkotor.exe"],
        cwd=official_dir)
    print(f"\n[1] official k1hrm applied -> md5 {md5(official)}")

    # --- 2. our port, for a fidelity diff ----------------------------------
    ourport = os.path.join(WORK, "ourport.exe")
    shutil.copyfile(UNIWS_BASE, ourport)
    hires_patch.patch(ourport, width, height,
                      letterbox=(letterbox.lower() not in ("no", "n", "0", "false")),
                      mapscale=False, backup_suffix=".hires-backup")
    regions, size_differs = diff_runs(official, ourport)
    verdict = "IDENTICAL" if not regions and not size_differs else "DIVERGES"
    print(f"[2] our k1hrm port vs official: {verdict} "
          f"({len(regions)} differing regions)")
    for s, e in regions:
        print(f"      0x{s:06X}-0x{e:06X}")

    # --- 3. our three layers on the official binary ------------------------
    full = os.path.join(WORK, "full.exe")
    shutil.copyfile(official, full)
    with open(full, "rb") as fh:
        data = bytearray(fh.read())
    matches = hires_patch.patch_map_scale(data, width, height)
    with open(full, "wb") as fh:
        fh.write(data)
    n_sites = sum(len(v) for v in matches.values())
    print(f"[3] mapscale + private floats: {n_sites} int16 sites written")

    py = sys.executable
    run([py, os.path.join(ROOT, "tools", "apply_marker_fix.py"),
         full, str(width), str(height)])
    run([py, os.path.join(ROOT, "tools", "apply_party_player_marker_fix.py"), full])
    print("[4] marker caves applied (note calibration, party, player)")
    run([py, os.path.join(ROOT, "tools", "pe_space.py"), "apply", full])
    run([py, os.path.join(ROOT, "tools", "note_table_patch.py"), "apply", full])
    print("[5] pe_space + note table applied")

    got = md5(full)
    print(f"\nRESULT  {os.path.relpath(full, ROOT)}")
    print(f"        size {os.path.getsize(full)}  md5 {got}")

    if os.path.isfile(LIVE):
        live_md5 = md5(LIVE)
        if got == live_md5:
            print(f"        EXACT MATCH for the live exe ({live_md5})")
        else:
            regions, _ = diff_runs(full, LIVE)
            print(f"        live exe md5 {live_md5} -- differs in "
                  f"{len(regions)} region(s):")
            for s, e in regions:
                note = "  <- k1hrm dialog letterbox" if s == 0x355788 else ""
                print(f"          0x{s:06X}-0x{e:06X} ({e - s + 1}B){note}")
    else:
        print("        (live exe not present; skipped comparison)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
