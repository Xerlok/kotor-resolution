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
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHER = os.path.join(ROOT, "patcher")
WORK = os.path.join(ROOT, "staging", "patcher-selftest")
GAME = os.path.join(WORK, "game")

BASE = os.path.join(ROOT, "staging", "verify-chain", "official", "swkotor.exe")
VANILLA = os.path.join(ROOT, "downloads", "swkotor.exe")
# k1hrm's own shipped 2560x1600 map.gui, to match BASE's resolution. Was the
# LIVE install's copy until 2026-08-30, which made the selftest depend on
# whatever resolution this machine happened to be patched for - it broke the
# moment Phase 4 rebuilt the install at 1920x1080. The shipped file is
# byte-identical to the live one (RELEASE_PLAN section 2.9, point 4: all 81
# files match), md5 4a9b423f4bf823f3b69405e0decf1e0f.
LIVE_GUI = os.path.join(ROOT, "downloads", "k1hrm-1.5", "16-by-10",
                        "gui.2560x1600", "map.gui")

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
        assert "two other mods have to go first" in out, out[-1500:]

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
        assert "menu files and your game don't match" in out, out[-1500:]

    def dry_run_writes_nothing():
        out = run("install.py", GAME, "--dry-run")
        assert "nothing was written to your game" in out
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

    def finishes_a_stale_k1hrm_exe():
        """The state every Windows user who runs hires_patcher.EXE ends up in.

        Roll k1hrm's four Area Map centring constants back to vanilla 640/480 -
        the exact 6-byte difference between hires_patcher.exe's output and
        hires_patcher.pl's - and require the patcher to notice and finish the
        job. The result must be the SAME in-game-confirmed exe, which is what
        makes this a fix rather than a guess. See F25.
        """
        sys.path.insert(0, PATCHER)
        from k1amf import detect
        stale = os.path.join(WORK, "stale-k1hrm")
        os.makedirs(os.path.join(stale, "Override"), exist_ok=True)
        shutil.copyfile(LIVE_GUI, os.path.join(stale, "Override", "map.gui"))
        with open(BASE, "rb") as fh:
            data = bytearray(fh.read())
        for offs, value in ((detect.CENTRING_X, detect.VANILLA_W),
                            (detect.CENTRING_Y, detect.VANILLA_H)):
            for off in offs:
                struct.pack_into("<h", data, off, value)
        assert detect.centring_state(data, 2560, 1600) == "stale"
        stale_exe = os.path.join(stale, "swkotor.exe")
        with open(stale_exe, "wb") as fh:
            fh.write(data)

        # --details, not the default: this note is log-only now (the patcher
        # just fixes it silently for the default player), so the proof that
        # it fired lives in the detail stream and in the md5 convergence
        # below, not in what a player sees on screen.
        out = run("install.py", stale, "--details")
        assert "left the map centring vanilla" in out, out[-1500:]
        for line in out.splitlines():
            if line.startswith("  [ ]"):
                raise SystemExit("a verification check failed:\n" + out[-3000:])
        got = md5(stale_exe)
        if got != EXPECTED_MD5:
            raise SystemExit(
                "finishing a stale k1hrm exe did not converge on the confirmed "
                "exe\n  expected %s\n  got      %s" % (EXPECTED_MD5, got))
        print("    detected, fixed, and converged on the confirmed exe")

    def refuses_unknown_centring():
        """Neither correct nor the known-stale state - we must not guess."""
        sys.path.insert(0, PATCHER)
        from k1amf import detect
        odd = os.path.join(WORK, "odd-centring")
        os.makedirs(os.path.join(odd, "Override"), exist_ok=True)
        shutil.copyfile(LIVE_GUI, os.path.join(odd, "Override", "map.gui"))
        with open(BASE, "rb") as fh:
            data = bytearray(fh.read())
        struct.pack_into("<h", data, detect.CENTRING_X[0], 1234)
        with open(os.path.join(odd, "swkotor.exe"), "wb") as fh:
            fh.write(data)
        out = run("install.py", odd, expect=1)
        assert "already changed the part of the game" in out, out[-1500:]

    case("refuses an exe k1hrm has not touched", refuses_without_k1hrm)
    case("refuses a .gui set from another resolution", refuses_mismatched_gui)
    case("--dry-run leaves the exe alone", dry_run_writes_nothing)
    case("rebuilds the in-game-confirmed exe byte for byte", applies_to_the_confirmed_exe)
    case("refuses to patch its own output again", refuses_to_patch_twice)
    case("revert restores the original bytes", reverts_exactly)
    case("reinstall after revert works", can_reinstall_after_revert)
    case("finishes a k1hrm exe left stale by hires_patcher.exe",
         finishes_a_stale_k1hrm_exe)
    case("refuses centring constants it does not recognise",
         refuses_unknown_centring)

    print("\nALL PASS - patcher output md5 %s" % EXPECTED_MD5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
