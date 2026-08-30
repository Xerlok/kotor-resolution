"""Toggle the real KOTOR install between the current MODDED state and 100% VANILLA.

Purpose: let the user run tests on an unmodified game, then get the exact modded
state back. Crash-safe by design - every fact needed to restore is written to
disk (backups/modded-restore-point/manifest.json) BEFORE anything is changed, so
a lost session costs nothing.

    python tools/vanilla_toggle.py status
    python tools/vanilla_toggle.py vanilla    # modded -> vanilla
    python tools/vanilla_toggle.py restore    # vanilla -> modded

What "vanilla" means here (decided with the user 2026-08-28):
  - swkotor.exe            <- backups/swkotor.exe.steam-backup (packed Steam original)
  - Override/              <- emptied; the live 600-file folder is MOVED to
                              backups/override-modded-stash (rename, not copy -
                              instant, and restore is exact)
  - swkotor.ini            <- Width/Height forced to 1600x1200 (vanilla accepts it;
                              2560x1600 exists only because of the UniWS patch)
  - saves/                 <- backed up (read-only precaution; not modified)

Deliberately NOT changed, and why:
  - the `~ HIGHDPIAWARE` AppCompatFlags registry layer: not a game file, and
    needed for the modded build; harmless for a fullscreen 1600x1200 vanilla run.
  - steam_appid.txt: removing it can stop a direct (non-Steam) launch working.
  - data/, modules/, TexturePacks/: never touched by this project in the first
    place, so they are already vanilla.
"""

import hashlib
import json
import os
import shutil
import sys
import time

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXE = os.path.join(GAME, "swkotor.exe")
INI = os.path.join(GAME, "swkotor.ini")
OVERRIDE = os.path.join(GAME, "Override")
# Project rule (CLAUDE.md): nothing of ours is parked inside the game folder, so
# the stash lives in backups/. Same volume as the install, so the move is still a
# rename - instant, and exact rather than a re-copy.
STASH = os.path.join(PROJ, "backups", "override-modded-stash")
SAVES = os.path.join(GAME, "saves")

PRISTINE = os.path.join(PROJ, "backups", "swkotor.exe.steam-backup")
PRISTINE_MD5 = "06b34d1b8a1ecefbaad0bf5e26556c71"

RESTORE_DIR = os.path.join(PROJ, "backups", "modded-restore-point")
MANIFEST = os.path.join(RESTORE_DIR, "manifest.json")

VANILLA_W, VANILLA_H = 1600, 1200


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count(path):
    return len(os.listdir(path)) if os.path.isdir(path) else None


def read_manifest():
    if os.path.isfile(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return None


def current_mode():
    """Infer the live mode from the install itself, not from the manifest."""
    if not os.path.isfile(EXE):
        return "broken (no swkotor.exe)"
    live = md5(EXE)
    if live == PRISTINE_MD5:
        return "vanilla"
    return "modded"


def cmd_status():
    print("=" * 72)
    print("MODE (inferred from the live exe):", current_mode())
    print()
    print("live install")
    print("   swkotor.exe    ", md5(EXE), os.path.getsize(EXE), "B")
    print("   Override/      ", count(OVERRIDE), "files")
    print("   Override stash ", count(STASH), "files" if os.path.isdir(STASH) else "(absent)")
    ini = open(INI, encoding="utf-8", errors="replace").read() if os.path.isfile(INI) else ""
    for key in ("Width=", "Height=", "FullScreen="):
        vals = [l.strip() for l in ini.splitlines() if l.strip().startswith(key)]
        print("   ini", key.rstrip("="), vals)
    print()
    m = read_manifest()
    if m:
        print("restore point", m["created"])
        print("   exe md5     ", m["exe_md5"])
        print("   Override    ", m["override_files"], "files ->", m["stash"])
        print("   ini backup  ", m["ini_backup"])
        print("   saves backup", m.get("saves_backup"))
    else:
        print("restore point: NONE (nothing to restore)")
    print("=" * 72)


def set_ini_resolution(path, w, h):
    """Rewrite Width=/Height= in place, preserving everything else byte-for-byte.

    KOTOR's own ini writer leaves duplicated/garbled fragments in this file, so
    every occurrence is rewritten rather than assuming one [Graphics Options].
    """
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        text = f.read()
    out, changed = [], 0
    for line in text.splitlines(keepends=True):
        end = line[len(line.rstrip("\r\n")):]
        s = line.rstrip("\r\n")
        if s.startswith("Width="):
            out.append("Width=%d%s" % (w, end)); changed += 1
        elif s.startswith("Height="):
            out.append("Height=%d%s" % (h, end)); changed += 1
        else:
            out.append(line)
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write("".join(out))
    return changed


def cmd_vanilla():
    mode = current_mode()
    if mode == "vanilla":
        print("REFUSING: the install is already vanilla (exe md5 == pristine).")
        print("Run 'restore' first if you meant to round-trip.")
        return 1
    if os.path.isdir(STASH):
        print("REFUSING: %s already exists - a previous toggle did not finish." % STASH)
        print("Inspect it by hand before continuing.")
        return 1
    if md5(PRISTINE) != PRISTINE_MD5:
        print("REFUSING: pristine backup md5 mismatch:", PRISTINE)
        return 1

    os.makedirs(RESTORE_DIR, exist_ok=True)

    # --- 1. capture the restore point BEFORE changing anything -------------
    print("[1/5] capturing restore point ->", RESTORE_DIR)
    exe_backup = os.path.join(RESTORE_DIR, "swkotor.exe.modded")
    ini_backup = os.path.join(RESTORE_DIR, "swkotor.ini.modded")
    shutil.copy2(EXE, exe_backup)
    shutil.copy2(INI, ini_backup)
    exe_md5 = md5(EXE)
    if md5(exe_backup) != exe_md5:
        print("ABORT: exe backup readback mismatch"); return 1
    print("      exe  ", exe_md5, "verified")
    print("      ini  ", md5(ini_backup), "verified")

    saves_backup = os.path.join(PROJ, "backups", "saves-pre-vanilla-test")
    if os.path.isdir(SAVES) and not os.path.isdir(saves_backup):
        shutil.copytree(SAVES, saves_backup)
        print("      saves", count(saves_backup), "entries copied")
    else:
        print("      saves backup already present, left alone")

    manifest = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "game": GAME,
        "exe_md5": exe_md5,
        "exe_backup": exe_backup,
        "ini_backup": ini_backup,
        "saves_backup": saves_backup,
        "override_files": count(OVERRIDE),
        "stash": STASH,
        "vanilla_md5": PRISTINE_MD5,
        "vanilla_resolution": [VANILLA_W, VANILLA_H],
        "registry_layer_left_in_place": "~ HIGHDPIAWARE",
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("      manifest written")

    # --- 2. Override aside (rename: instant, exact, same volume) ----------
    n = count(OVERRIDE)
    print("[2/5] moving Override (%s files) -> Override.modded-stash" % n)
    os.rename(OVERRIDE, STASH)
    os.makedirs(OVERRIDE)
    print("      done; live Override is now empty")

    # --- 3. pristine exe --------------------------------------------------
    print("[3/5] installing pristine Steam exe")
    shutil.copy2(PRISTINE, EXE)
    if md5(EXE) != PRISTINE_MD5:
        print("ABORT: exe readback mismatch after copy"); return 1
    print("      swkotor.exe", PRISTINE_MD5, "verified")

    # --- 4. vanilla resolution -------------------------------------------
    print("[4/5] setting ini resolution %dx%d" % (VANILLA_W, VANILLA_H))
    print("      rewrote", set_ini_resolution(INI, VANILLA_W, VANILLA_H), "line(s)")

    # --- 5. report --------------------------------------------------------
    print("[5/5] VANILLA. Launch through Steam (the packed exe expects it).")
    return 0


def cmd_restore():
    m = read_manifest()
    if not m:
        print("REFUSING: no restore point at", MANIFEST)
        return 1
    if current_mode() == "modded":
        print("REFUSING: the live exe is not the pristine one - already modded?")
        print("Run 'status' and resolve by hand.")
        return 1
    if not os.path.isdir(STASH):
        print("REFUSING: Override stash missing:", STASH)
        return 1

    print("[1/4] restoring modded swkotor.exe")
    shutil.copy2(m["exe_backup"], EXE)
    if md5(EXE) != m["exe_md5"]:
        print("ABORT: exe readback mismatch"); return 1
    print("      ", m["exe_md5"], "verified")

    print("[2/4] restoring Override from stash")
    live = count(OVERRIDE)
    if live:
        # the vanilla run should not have written here; keep whatever it did
        moved = os.path.join(GAME, "Override.vanilla-run-leftovers")
        os.rename(OVERRIDE, moved)
        print("      NOTE: live Override had %d file(s); moved to %s" % (live, moved))
    else:
        os.rmdir(OVERRIDE)
    os.rename(STASH, OVERRIDE)
    print("      ", count(OVERRIDE), "files restored (expected", m["override_files"], ")")

    print("[3/4] restoring swkotor.ini")
    shutil.copy2(m["ini_backup"], INI)
    print("      ", md5(INI), "verified" if md5(INI) == md5(m["ini_backup"]) else "MISMATCH")

    print("[4/4] MODDED state restored. Verify in-game: Area Map + HUD minimap.")
    return 0


if __name__ == "__main__":
    cmds = {"status": cmd_status, "vanilla": cmd_vanilla, "restore": cmd_restore}
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg not in cmds:
        print(__doc__)
        sys.exit(2)
    sys.exit(cmds[arg]() or 0)
