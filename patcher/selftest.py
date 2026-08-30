"""The patcher's acceptance test: does it rebuild the exe we confirmed in game?

    python patcher/selftest.py

The bar is not "it runs". It is that patching the official UniWS + k1hrm output
with THIS patcher produces `435108fdb65bac2151ab694e7fb8e36a` - byte for byte
the exe that has been played and checked in game (RELEASE_PLAN.md section 2.9).
Anything that changes a written byte, in any of the five layers or in the order
they run, fails here.

It also checks the refusals, because a patcher that only works on the happy path
is not shippable: a non-k1hrm exe, a mismatched .gui set, a second run over its
own work, and a revert that must come back to the exact starting bytes.

Fixtures come from staging/ and the live install; nothing here writes to either.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHER = os.path.join(ROOT, "patcher")
WORK = os.path.join(ROOT, "staging", "patcher-selftest")
GAME = os.path.join(WORK, "game")

BASE = os.path.join(ROOT, "staging", "verify-chain", "official", "swkotor.exe")
VANILLA = os.path.join(ROOT, "downloads", "swkotor.exe")
LIVE_GUI = (r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
            r"\Override\map.gui")

EXPECTED_MD5 = "435108fdb65bac2151ab694e7fb8e36a"   # the live, in-game-confirmed exe


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def run(script, *args, expect=0):
    env = dict(os.environ, K1AMF_HOME=WORK, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(PATCHER, script), *args],
                       capture_output=True, text=True, env=env, cwd=PATCHER)
    if r.returncode != expect:
        print(r.stdout[-4000:])
        print(r.stderr[-2000:])
        raise SystemExit("%s %s exited %d, expected %d"
                         % (script, " ".join(args), r.returncode, expect))
    return r.stdout


def fixture():
    """A throwaway game folder: official-chain exe + the matching .gui set."""
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(os.path.join(GAME, "Override"))
    shutil.copyfile(BASE, os.path.join(GAME, "swkotor.exe"))
    shutil.copyfile(LIVE_GUI, os.path.join(GAME, "Override", "map.gui"))
    return os.path.join(GAME, "swkotor.exe")


def case(label, fn):
    print("\n=== %s" % label)
    fn()
    print("    PASS")


def main():
    for need in (BASE, LIVE_GUI):
        if not os.path.isfile(need):
            raise SystemExit("missing fixture: %s" % need)

    exe = fixture()
    base_md5 = md5(exe)
    print("base (UniWS + official k1hrm): %s  md5 %s" % (os.path.getsize(exe), base_md5))

    def refuses_without_k1hrm():
        if not os.path.isfile(VANILLA):
            print("    skipped: %s not present" % VANILLA)
            return
        stray = os.path.join(WORK, "vanilla")
        os.makedirs(os.path.join(stray, "Override"), exist_ok=True)
        shutil.copyfile(VANILLA, os.path.join(stray, "swkotor.exe"))
        shutil.copyfile(LIVE_GUI, os.path.join(stray, "Override", "map.gui"))
        out = run("install.py", stray, expect=1)
        assert "k1hrm" in out and "has not been run" in out, out[-1500:]

    def refuses_mismatched_gui():
        odd = os.path.join(WORK, "wronggui")
        os.makedirs(os.path.join(odd, "Override"), exist_ok=True)
        shutil.copyfile(BASE, os.path.join(odd, "swkotor.exe"))
        # a .gui from a different resolution: shrink LBL_Map by 100 px
        sys.path.insert(0, ROOT)
        from tools import gff, gff_writer
        from tools.map_frame_fix import find_control, set_extent, read_extent
        g = gff.load(LIVE_GUI)
        ctrl = find_control(g.top, "LBL_Map")
        left, top, width, height = read_extent(ctrl)
        set_extent(ctrl, (left, top, width - 100, height))
        with open(os.path.join(odd, "Override", "map.gui"), "wb") as fh:
            fh.write(gff_writer.dumps(g))
        out = run("install.py", odd, expect=1)
        assert "different resolution" in out, out[-1500:]

    def dry_run_writes_nothing():
        out = run("install.py", GAME, "--dry-run")
        assert "nothing was written" in out
        assert md5(exe) == base_md5

    def applies_to_the_confirmed_exe():
        out = run("install.py", GAME)
        for line in out.splitlines():
            if line.startswith("  [ ]"):
                raise SystemExit("a verification check failed:\n" + out[-3000:])
        got = md5(exe)
        print("    patched md5 %s" % got)
        if got != EXPECTED_MD5:
            raise SystemExit(
                "patcher output differs from the in-game-confirmed exe\n"
                "  expected %s\n  got      %s" % (EXPECTED_MD5, got))
        print("    byte-identical to the live, in-game-confirmed exe")

    def refuses_to_patch_twice():
        out = run("install.py", GAME)
        assert "already installed" in out, out[-1500:]
        assert md5(exe) == EXPECTED_MD5

    def reverts_exactly():
        run("revert.py")
        got = md5(exe)
        if got != base_md5:
            raise SystemExit("revert left %s, expected the original %s"
                             % (got, base_md5))
        print("    back to the pre-patch bytes exactly")

    def can_reinstall_after_revert():
        run("install.py", GAME)
        assert md5(exe) == EXPECTED_MD5

    case("refuses an exe k1hrm has not touched", refuses_without_k1hrm)
    case("refuses a .gui set from another resolution", refuses_mismatched_gui)
    case("--dry-run leaves the exe alone", dry_run_writes_nothing)
    case("rebuilds the in-game-confirmed exe byte for byte", applies_to_the_confirmed_exe)
    case("refuses to patch its own output again", refuses_to_patch_twice)
    case("revert restores the original bytes", reverts_exactly)
    case("reinstall after revert works", can_reinstall_after_revert)

    print("\nALL PASS - patcher output md5 %s" % EXPECTED_MD5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
