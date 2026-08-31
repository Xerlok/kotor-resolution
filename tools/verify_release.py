"""Acceptance test for the PACKAGED release, not for the source. Phase 6.

    python tools/verify_release.py

patcher/selftest.py proves the *source* patcher reproduces the exe this project
confirmed in game. It cannot prove the frozen build does: freezing is its own
failure surface, and two real defects were found here by running the packaged
artifact rather than the source -

  * PyInstaller collected keystone's Python files but not keystone.dll, so the
    assembler fell through to a distutils fallback that Python 3.12 removed;
  * the frozen build wrote the player's only backup of their exe into
    PyInstaller's `_internal` folder.

Neither is reachable from selftest.py. So this runs the shipped .exe files
end to end against a throwaway game folder and requires the same md5 the source
patcher and the in-game-confirmed build both produce.

The release is copied to staging first, so the test never leaves an
installed.json or a backup inside the artifact that gets zipped and published.
%LOCALAPPDATA% is redirected into staging too, for the same reason and because
that is now where the player's backup goes - see manifest._data_home().

Four things beyond "does it patch" are checked here because they are promises
made to the player rather than properties of the bytes:

  * the backup and the install record land outside the mod folder, and the mod
    still uninstalls after that folder has been deleted and re-downloaded;
  * install and uninstall both work with no Python anywhere on the machine;
  * running from inside the zip is refused rather than half-working;
  * the game folder is left with nothing of ours in it.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "patcher"))

from k1amf import PRODUCT, __version__          # noqa: E402
import selftest as st                            # noqa: E402

# The exe this project confirmed in game, and that patcher/selftest.py pins.
CONFIRMED_MD5 = "435108fdb65bac2151ab694e7fb8e36a"

RELEASE = os.path.join(ROOT, "dist", "K1-Area-Map-Fixes-%s" % __version__)
SANDBOX = os.path.join(ROOT, "staging", "release-check")
# %LOCALAPPDATA% for the patcher under test. Redirected rather than mocked, so
# the path the player actually gets is the path being exercised - and so a test
# run never touches the real one.
FAKE_LOCALAPPDATA = os.path.join(ROOT, "staging", "release-check-appdata")
# A stand-in for the folder a zip viewer extracts into, for the temp refusal.
FAKE_TEMP = os.path.join(ROOT, "staging", "release-check-temp")
FROZEN_DIR = "Patcher"
EXTRAS_DIR = "More info"
DATA_NAME = "K1AreaMapFixes"

TOP_LEVEL = ["Install.bat", EXTRAS_DIR, FROZEN_DIR, "README.txt",
             "Uninstall.bat"]

failures = []


def env_for(**over):
    """The child's environment: our LOCALAPPDATA, and no K1AMF_HOME.

    K1AMF_HOME would override the location this test exists to check, and a
    development shell may well have it set.
    """
    env = dict(os.environ, LOCALAPPDATA=FAKE_LOCALAPPDATA,
               PYTHONIOENCODING="utf-8")
    env.pop("K1AMF_HOME", None)
    env.update(over)
    return env


def bare_env():
    """An environment with no Python reachable at all.

    The question this answers is a user's: does the mod install and uninstall on
    a machine that has never had Python on it? Stripping PATH down to the two
    Windows directories is the closest this repo can get to that machine without
    a clean VM - anything the frozen build needs beyond its own folder and the
    system directory fails here.
    """
    keep = ("SystemRoot", "windir", "ComSpec", "PATHEXT", "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE", "USERPROFILE", "TEMP", "TMP")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    system32 = os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32")
    env["PATH"] = system32 + os.pathsep + env.get("SystemRoot", r"C:\Windows")
    env["LOCALAPPDATA"] = FAKE_LOCALAPPDATA
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("x" if ok else " ", label,
                           "" if ok else "   <-- FAILED %s" % detail))
    if not ok:
        failures.append(label)


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def main():
    if not os.path.isdir(RELEASE):
        raise SystemExit("no release at %s - run tools/build_release.py first"
                         % RELEASE)

    print("%s %s - packaged release acceptance test" % (PRODUCT, __version__))
    print("release: %s" % RELEASE)

    for stale in (SANDBOX, FAKE_LOCALAPPDATA, FAKE_TEMP):
        if os.path.isdir(stale):
            shutil.rmtree(stale)
    shutil.copytree(RELEASE, SANDBOX)
    frozen = os.path.join(SANDBOX, FROZEN_DIR)
    extras = os.path.join(SANDBOX, EXTRAS_DIR)

    print("\n-- what the player sees -------------------------------------")
    top = sorted(os.listdir(SANDBOX))
    check("the top level is only what a player needs (%d entries)" % len(top),
          top == TOP_LEVEL, top)
    for name in ("COMPATIBILITY.txt", "TROUBLESHOOTING.txt", "TECHNICAL.txt",
                 "LICENSE", "SHA256SUMS.txt"):
        check("%s\\%s ships" % (EXTRAS_DIR, name),
              os.path.isfile(os.path.join(extras, name)))
    check("keystone.dll is bundled where keystone.py looks for it",
          os.path.isfile(os.path.join(frozen, "_internal", "keystone",
                                      "keystone.dll")))
    check("selftest.py is NOT shipped (it needs a fixture no player has)",
          not os.path.isfile(os.path.join(extras, "source", "selftest.py")))

    print("\n-- the Python source the README offers as an escape hatch ---")
    src = os.path.join(extras, "source", "install.py")
    check("source\\install.py ships", os.path.isfile(src))
    # It refuses (no game folder here), but a refusal proves every import
    # resolved. A missing tools module would surface on stderr instead - which
    # is exactly how this shipped broken once.
    dry = subprocess.run([sys.executable, src, "--dry-run"],
                         capture_output=True, text=True, cwd=SANDBOX,
                         env=env_for())
    check("source\\install.py runs - no missing module",
          "ModuleNotFoundError" not in dry.stderr
          and "ImportError" not in dry.stderr,
          dry.stderr.strip().splitlines()[-1] if dry.stderr.strip() else "")
    # Nothing in the shipped patcher shells out, so nothing outside the box can
    # be missing from a player's machine. Static half of "is Python optional?".
    shells = []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(extras, "source")):
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                body = fh.read()
            for token in ("subprocess", "os.system", "os.popen", "shutil.which"):
                if token in body:
                    shells.append("%s: %s" % (fn, token))
    check("no shipped module shells out to anything", not shells, shells)

    exe = st.fixture()
    game = os.path.dirname(exe)
    base = md5(exe)
    data_dir = os.path.join(FAKE_LOCALAPPDATA, DATA_NAME)
    install_exe = os.path.join(frozen, "K1AreaMapFixes.exe")
    revert_exe = os.path.join(frozen, "K1AreaMapFixes-Revert.exe")

    print("\n-- apply, from the frozen build -----------------------------")
    r = subprocess.run([install_exe, game], capture_output=True, text=True,
                       env=env_for())
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-1000:])
    check("the frozen patcher ran and reported success", r.returncode == 0)
    check("it told the player nothing clashes, in plain words",
          "Nothing installed that clashes" in r.stdout)
    # A real hex address, not the "0x1600" inside "2560x1600".
    hexes = re.findall(r"(?<![0-9A-Za-z])0x[0-9A-Fa-f]{3,}", r.stdout)
    check("the default output has no hex addresses in it",
          not hexes, "found %s" % hexes[:3])
    check("a full technical log was written for bug reports",
          os.path.isfile(os.path.join(SANDBOX, "last-run-log.txt")))
    check("the patched exe is the build confirmed in game (md5 %s)"
          % CONFIRMED_MD5, md5(exe) == CONFIRMED_MD5, md5(exe))

    print("\n-- where a player's backup landed ---------------------------")
    backup = os.path.join(data_dir, "backup", "swkotor.exe.original")
    check("the install record is in %%LOCALAPPDATA%%\\%s" % DATA_NAME,
          os.path.isfile(os.path.join(data_dir, "installed.json")))
    check("the original exe is backed up there too", os.path.isfile(backup))
    check("the backup is the player's real pre-patch exe",
          os.path.isfile(backup) and md5(backup) == base)
    now = sorted(os.listdir(SANDBOX))
    check("the mod folder gained only last-run-log.txt",
          now == sorted(TOP_LEVEL + ["last-run-log.txt"]), now)
    check("nothing was written inside _internal",
          not os.path.isfile(os.path.join(frozen, "_internal",
                                          "installed.json")))
    check("nothing of ours was left in the game folder",
          sorted(os.listdir(game)) == ["Override", "swkotor.exe"],
          sorted(os.listdir(game)))

    print("\n-- refuses to patch twice -----------------------------------")
    again = subprocess.run([install_exe, game], capture_output=True, text=True,
                           env=env_for())
    check("a second apply is refused, exe untouched",
          "already installed" in again.stdout and md5(exe) == CONFIRMED_MD5)

    print("\n-- the download is deleted, then the mod is uninstalled -----")
    # The promise the relocated backup exists to keep: a player who installed
    # out of their Downloads folder and then cleared it can still get their
    # game back from a fresh copy of the same release.
    shutil.rmtree(SANDBOX)
    shutil.copytree(RELEASE, SANDBOX)
    r2 = subprocess.run([revert_exe, game], capture_output=True, text=True,
                        env=env_for())
    if r2.returncode != 0:
        print(r2.stdout[-1500:])
        print(r2.stderr[-1000:])
    check("the frozen uninstaller ran from a re-downloaded copy",
          r2.returncode == 0)
    check("the exe is back to its exact pre-patch bytes", md5(exe) == base,
          "%s != %s" % (md5(exe), base))

    print("\n-- with no Python on the machine at all ---------------------")
    lean = bare_env()
    check("the test is meaningful: no python on this PATH",
          shutil.which("python", path=lean["PATH"]) is None
          and shutil.which("py", path=lean["PATH"]) is None)
    r3 = subprocess.run([install_exe, game], capture_output=True, text=True,
                        env=lean)
    if r3.returncode != 0:
        print(r3.stdout[-2000:])
        print(r3.stderr[-1000:])
    check("it installs with no Python present", r3.returncode == 0)
    check("and produces the same confirmed exe", md5(exe) == CONFIRMED_MD5,
          md5(exe))
    r4 = subprocess.run([revert_exe, game], capture_output=True, text=True,
                        env=lean)
    if r4.returncode != 0:
        print(r4.stdout[-1500:])
        print(r4.stderr[-1000:])
    check("it uninstalls with no Python present", r4.returncode == 0)
    check("and the exe is byte-exact again", md5(exe) == base,
          "%s != %s" % (md5(exe), base))

    print("\n-- run from inside the zip ----------------------------------")
    # What Explorer does when you double-click Install.bat while looking at the
    # zip: extract to %TEMP%\Temp1_<zipname>\ and run it there.
    zipdir = os.path.join(FAKE_TEMP, "Temp1_K1-Area-Map-Fixes-%s" % __version__)
    shutil.copytree(RELEASE, zipdir)
    r5 = subprocess.run([os.path.join(zipdir, FROZEN_DIR,
                                      "K1AreaMapFixes.exe"), game],
                        capture_output=True, text=True,
                        env=env_for(TEMP=FAKE_TEMP, TMP=FAKE_TEMP))
    check("running from a temp folder is refused", r5.returncode == 1
          and "Unzip the download first" in r5.stdout, r5.stdout[-400:])
    check("the refusal left the game alone", md5(exe) == base)

    print("")
    if failures:
        print("FAILED: %d" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("ALL PASS - the packaged release patches to %s and reverts clean"
          % CONFIRMED_MD5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
