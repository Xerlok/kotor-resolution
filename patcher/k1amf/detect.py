"""Find the game, read the resolution out of the exe, and gate on prerequisites.

The design point (RELEASE_PLAN.md section 5.1): **never ask the player for their
resolution.** k1hrm writes the real width/height over the engine's hardcoded
+-640/+-480 canvas constants, so the exe already knows, and reading it there
turns "did you install the matching .gui set?" - the most common failure in this
whole mod category - into something the patcher can check instead of something
the player can get wrong.
"""
from __future__ import annotations

import hashlib
import os
import struct
import tempfile

from . import _toolpath  # noqa: F401  (side effect: tools/ on sys.path)

import hires_patch
import pe_space


class Refusal(Exception):
    """A prerequisite is not met. The message is written for the player."""


# --- what we accept ------------------------------------------------------
# The Editable Executable (the one UniWS and k1hrm are made for), before our
# layer. UniWS and k1hrm both patch in place, so the size is unchanged; ours is
# the only step that grows the file (pe_space, +0x2000).
BASE_SIZE = 4_042_752
PATCHED_SIZE = BASE_SIZE + pe_space.REGION_BYTES

# k1hrm writes -width / -height over these (menu buttons, then list/scrollbar
# hit-testing) and +width / +height over those. The gog-build offsets; other
# builds use different ones, which is exactly why the size gate above comes
# first. CONFIRMED on the official-chain exe 2026-08-30: all four read
# -2560/-1600 and both positives read 2560/1600.
NEG_X, NEG_Y = (0xB6C7, 0xBA6C), (0xB6DA, 0xBA83)
POS_X, POS_Y = (0xAA65,), (0xAA85,)
VANILLA_W, VANILLA_H = 640, 480

# k1hrm's positive_offsets_x / _y hold THREE gog offsets each, not one. The other
# two of each are int16 immediates inside the Area Map GUI code, where the engine
# offsets the map by (screen - CONST)/2:
#
#     0x692958  sub eax, 0x280            ; 640
#     0x69295D  cdq / sub eax,edx / sar eax,1
#     0x692964  add esi, eax              ; esi += (screenW - 640)/2
#
# k1hrm overwrites 640/480 with the target resolution so that term becomes zero.
# Its shipped hires_patcher.EXE does not - only hires_patcher.PL does. The two
# differ by exactly 6 bytes, all of them here, and k1hrm's .bat and README both
# point Windows users at the .exe. Left vanilla, the Area Map art is drawn
# ((W-640)/2, (H-480)/2) off its box: measured (642, 300) at 1920x1080 against
# (0, 0) on the confirmed-good 2560x1600 build. See F25 in
# docs/EXPERIMENTS_AND_FAILED_APPROACHES.md. Same gog build as POS_X/POS_Y above,
# so the BASE_SIZE gate already covers "is this that build".
CENTRING_X = (0x2928B3, 0x292959)
CENTRING_Y = (0x2928C3, 0x29296B)

MIN_W, MAX_W = 640, 7680
MIN_H, MAX_H = 480, 4320

# `hires_patch.MAP_OFFSETS` lists 17 int16 sites, but "map_grid" at 0x17906F
# holds 1401 in the PRISTINE exe, not the 32 the table expects - that offset
# belongs to a different exe build, inherited from hires_patcher.pl's per-build
# offset lists. It has therefore never matched and never been written: not by
# k1hrm, not by our port, and not in the exe this project confirmed in game.
# Excluded here so "how many bytes should change" is an exact number rather than
# "however many happen to match", and so that an exe where it DOES match is
# refused as an unknown build instead of being written for the first time by a
# player. VERIFIED 2026-08-30 against downloads/swkotor.exe (untouched),
# backups/swkotor.exe.uniws-only-backup, and the official-chain exe.
SKIP_SITES = {0x17906F}

MAP_GUI = os.path.join("Override", "map.gui")
GUI_TOLERANCE = 1          # 3 of k1hrm's 49 sets differ from the formula by 1 px


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def scale_sites():
    """(key, offset, struct format, vanilla default) for every int16 site this
    patcher actually writes - MAP_OFFSETS minus SKIP_SITES."""
    for key, (offs, tpl, default) in hires_patch.MAP_OFFSETS.items():
        for off in offs:
            if off not in SKIP_SITES:
                yield key, off, tpl, default


SCALE_SITE_COUNT = sum(1 for _ in scale_sites())     # 16


# --- where is the game ---------------------------------------------------
def _steam_libraries():
    """Steam library roots, from the registry and libraryfolders.vdf."""
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots.append(r"C:\Program Files (x86)\Steam")

    libs = []
    for root in roots:
        if root and os.path.isdir(root) and root not in libs:
            libs.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    parts = line.split('"')
                    # ..."path"  "D:\\SteamLibrary"...
                    if len(parts) >= 5 and parts[1] == "path":
                        p = parts[3].replace("\\\\", "\\")
                        if os.path.isdir(p) and p not in libs:
                            libs.append(p)
        except OSError:
            pass
    return libs


def candidate_game_dirs(start=None):
    """Every plausible install folder, most likely first."""
    out = []

    def add(p):
        if p and os.path.isdir(p) and p not in out:
            out.append(p)

    # 1. wherever the patcher was unpacked, and its parent - players do drop
    #    mod folders straight into the game directory
    if start:
        add(start)
        add(os.path.dirname(os.path.abspath(start)))
    # 2. Steam, including non-default library drives
    for lib in _steam_libraries():
        add(os.path.join(lib, "steamapps", "common", "swkotor"))
    # 3. GOG and retail defaults
    for p in (r"C:\GOG Games\Star Wars - KotOR",
              r"C:\Program Files (x86)\GOG Galaxy\Games\Star Wars - KotOR",
              r"C:\Program Files (x86)\LucasArts\SWKotOR",
              r"C:\Program Files\LucasArts\SWKotOR"):
        add(p)
    return out


def find_game_dir(explicit=None, start=None):
    """The game folder, or a Refusal that says how to point us at it."""
    if explicit:
        exe = os.path.join(explicit, "swkotor.exe")
        if not os.path.isfile(exe):
            raise Refusal(
                "That folder doesn't have swkotor.exe in it:\n"
                "    %s\n"
                "\n"
                "I need the folder the game itself is in - the one with\n"
                "swkotor.exe, and folders called Override and modules." % explicit)
        return explicit
    for cand in candidate_game_dirs(start):
        if os.path.isfile(os.path.join(cand, "swkotor.exe")):
            return cand
    raise Refusal(
        "I couldn't find your KOTOR folder.\n"
        "\n"
        "Easiest fix: drag your KOTOR folder onto Install.bat and let go.\n"
        "\n"
        "That's the folder with swkotor.exe in it, usually something like\n"
        "    C:\\Program Files (x86)\\Steam\\steamapps\\common\\swkotor")


# --- other mods we know we fight with -----------------------------------
# Kotor Patch Manager's KotorUniResPatch hooks CSWGuiMapHider::Draw at runtime
# and re-scales the Area Map using the same two shared constants we scale
# (0x747748 / 0x7455D4), so with both live the map is scaled twice. Nothing of
# it is on disk in the exe - it allocates its own code at load - so we cannot
# gate on bytes; these are the files its installer leaves behind.
#
# We WARN rather than refuse (decision 2026-08-30). KPM is a patch *manager*:
# its presence does not prove the UniRes patch is enabled, the clash is
# cosmetic and reversible on both sides, and refusing would block people who
# use KPM for unrelated patches.
KPM_FILES = ("KotorPatcher.dll", "KPatchLauncher.exe", "hooks.toml",
             "manifest.toml", "patch_config.toml")


def conflicting_mods(game_dir):
    """Warnings (not refusals) about mods on disk that fight with this one."""
    seen = [n for n in KPM_FILES if os.path.isfile(os.path.join(game_dir, n))]
    if not seen:
        return []
    return [
        "Heads up: Kotor Patch Manager is installed here.",
        "  If you have its \"KotorUniResPatch\" switched on, turn it off. It",
        "  fixes the same map this mod does, and with both on the map comes",
        "  out wrong. Nothing else in Kotor Patch Manager is affected.",
        "  Carrying on with the install.",
        "  (Found: %s)" % ", ".join(seen),
    ]


# --- are we running from inside the zip ---------------------------------
# Double-clicking a .bat while looking at a zip in Explorer does not fail: it
# extracts to %TEMP%\Temp1_<zipname>\ and runs there. 7-Zip (%TEMP%\7z*) and
# WinRAR (%TEMP%\Rar$*) do the same from their own viewers. Windows empties
# those folders whenever it likes, so Uninstall.bat and last-run-log.txt are
# gone by the time they are wanted - the beginner-killer documented in
# TROUBLESHOOTING.txt. The backup no longer lives there (manifest._data_home),
# so this is a backstop rather than the fix, and it is cheap: every one of them
# lands under a temp root.
def temp_roots():
    """Directories a zip viewer might have extracted us into."""
    roots = [tempfile.gettempdir(),
             os.environ.get("TEMP"), os.environ.get("TMP")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Temp"))
    win = os.environ.get("SystemRoot") or os.environ.get("windir")
    if win:
        roots.append(os.path.join(win, "Temp"))
    out = []
    for root in roots:
        if not root:
            continue
        try:
            root = os.path.normcase(os.path.realpath(root))
        except OSError:
            continue
        if root not in out:
            out.append(root)
    return out


def in_temp_folder(path):
    path = os.path.normcase(os.path.realpath(path))
    for root in temp_roots():
        if path == root or path.startswith(root + os.sep):
            return True
    return False


def check_not_temp(folder):
    """Refuse to install from a temp folder, naming the fix first."""
    if not in_temp_folder(folder):
        return
    raise Refusal(
        "Unzip the download first, then run Install.bat from the unzipped\n"
        "folder.\n"
        "\n"
        "This is running from a temporary folder Windows made for it:\n"
        "    %s\n"
        "\n"
        "That happens when you open the zip and double-click Install.bat\n"
        "inside it, without unzipping first. Windows deletes that folder\n"
        "whenever it feels like it, and Uninstall.bat would go with it.\n"
        "\n"
        "Right-click the zip file, choose \"Extract All...\", put the folder\n"
        "somewhere you'll keep it - your Desktop is fine - and run\n"
        "Install.bat from in there." % folder)


# Three different gates end up here: the menu-size values disagree with each
# other, they say something impossible, or the map centring values are neither
# correct nor the one wrong state we know how to finish. Same cause every time
# - something has already edited this part of the game - and the same fix, so
# they say the same thing rather than three variations a player has to tell
# apart. The specific values follow in brackets; that is what a bug report
# needs, and it reads as detail rather than as the headline.
_MEDDLED = (
    "Something has already changed the part of the game this mod patches,\n"
    "and I don't recognise what it did.\n"
    "\n"
    "I'm not going to guess and risk breaking your game. The safe fix is to\n"
    "start clean:\n"
    "\n"
    "  1. put back an unmodified swkotor.exe (or reinstall the Editable\n"
    "     Executable)\n"
    "  2. run UniWS, then the high-res menus mod\n"
    "  3. run this again")


# --- is this the build we know ------------------------------------------
def check_build(data, exe_path):
    if len(data) == PATCHED_SIZE and pe_space.find_region(data):
        return          # already ours; layer_state() reports it properly
    if len(data) != BASE_SIZE:
        raise Refusal(
            "This isn't the version of the game this mod can patch.\n"
            "\n"
            "The Steam and GOG releases ship a swkotor.exe that no mod can\n"
            "patch - not this one, not UniWS, not the high-res menus mod.\n"
            "Everyone gets around it the same way: install the \"KOTOR\n"
            "Editable Executable\" first. It's a free download on\n"
            "DeadlyStream and it's the normal first step for this kind of\n"
            "mod. Then run UniWS and the high-res menus mod, then this.\n"
            "\n"
            "(Your swkotor.exe is %d bytes; the one I'm expecting is %d.)"
            % (len(data), BASE_SIZE))


# --- what resolution is this exe patched for ----------------------------
def _int32(data, off):
    return struct.unpack_from("<i", data, off)[0]


def read_resolution(data):
    """(width, height) as k1hrm wrote them, or a Refusal explaining what is off."""
    neg_x = [-_int32(data, o) for o in NEG_X]
    neg_y = [-_int32(data, o) for o in NEG_Y]
    pos_x = [_int32(data, o) for o in POS_X]
    pos_y = [_int32(data, o) for o in POS_Y]
    xs, ys = neg_x + pos_x, neg_y + pos_y

    if set(xs) == {VANILLA_W} and set(ys) == {VANILLA_H}:
        raise Refusal(
            "Not ready yet - two other mods have to go first.\n"
            "\n"
            "This mod only fixes the map. It doesn't change your resolution,\n"
            "and it can't run until the mods that do are in place:\n"
            "\n"
            "  1. UniWS                        makes the game offer your\n"
            "                                  resolution\n"
            "  2. KotOR High Resolution Menus  redraws the menus to fit it\n"
            "     (k1hrm, by ndix UR)\n"
            "  3. this mod\n"
            "\n"
            "Your game still has the original 640x480 menu sizes, so step 2\n"
            "hasn't been done. Install those two, then run this again.\n"
            "\n"
            "The README has the full list with links.")

    if len(set(xs)) != 1 or len(set(ys)) != 1:
        raise Refusal(_MEDDLED + "\n\n(Menu size values found: %s / %s.)"
                      % (xs, ys))

    width, height = xs[0], ys[0]
    if not (MIN_W <= width <= MAX_W and MIN_H <= height <= MAX_H):
        raise Refusal(_MEDDLED + "\n\n(The resolution I read out of the game "
                      "was %dx%d, which can't be right.)" % (width, height))
    return width, height


# --- did k1hrm finish the job -------------------------------------------
def centring_state(data, width, height):
    """'ok', 'stale' or 'unknown' for k1hrm's four Area Map centring constants.

    'stale' means k1hrm ran (the canvas constants already proved that) but its
    shipped .exe left these four at vanilla - the state every Windows user who
    follows k1hrm's own instructions ends up in.
    """
    got_x = [struct.unpack_from("<h", data, o)[0] for o in CENTRING_X]
    got_y = [struct.unpack_from("<h", data, o)[0] for o in CENTRING_Y]
    if all(v == width for v in got_x) and all(v == height for v in got_y):
        return "ok"
    if all(v == VANILLA_W for v in got_x) and all(v == VANILLA_H for v in got_y):
        return "stale"
    return "unknown"


def check_centring(data, width, height):
    """Refuse anything that is neither correct nor exactly the known-stale state.

    We are willing to finish k1hrm's job, but only from the one starting point we
    have measured. Any other value means something else has edited these bytes,
    and guessing would be writing into a subsystem on no evidence.
    """
    state = centring_state(data, width, height)
    if state == "unknown":
        got = ([struct.unpack_from("<h", data, o)[0] for o in CENTRING_X],
               [struct.unpack_from("<h", data, o)[0] for o in CENTRING_Y])
        raise Refusal(
            _MEDDLED + "\n\n(The map centring values read %s / %s. I expected "
            "either %dx%d or %dx%d.)"
            % (got[0], got[1], width, height, VANILLA_W, VANILLA_H))
    return state


# --- does the .gui set match the exe ------------------------------------
def expected_map_extent(width, height):
    """k1hrm's own LBL_Map box: (95*kx, 118*ky, 440*kx, 256*ky)."""
    kx, ky = width / 640.0, height / 480.0
    r = hires_patch._round_half_up
    return (r(95 * kx), r(118 * ky), r(440 * kx), r(256 * ky))


def read_map_extent(game_dir):
    """LBL_Map's EXTENT from Override/map.gui."""
    import gff
    path = os.path.join(game_dir, MAP_GUI)
    if not os.path.isfile(path):
        raise Refusal(
            "A menu file the game needs is missing:\n"
            "    %s\n"
            "\n"
            "The high-res menus mod puts it there, along with the rest of the\n"
            "menu files for your resolution. Run that mod first, and make sure\n"
            "you copy its menu files into your Override folder." % MAP_GUI)
    g = gff.load(path)

    def val(v):
        return v.value if hasattr(v, "value") else v

    for c in val(g.top.fields.get("CONTROLS")) or []:
        if val(c.fields.get("TAG")) == "LBL_Map":
            ef = val(c.fields["EXTENT"]).fields
            return tuple(int(val(ef[k])) for k in ("LEFT", "TOP", "WIDTH", "HEIGHT"))
    raise Refusal(
        "This file isn't a KOTOR map screen:\n"
        "    %s\n"
        "\n"
        "Something has replaced it with a different file. Re-copy the menu\n"
        "files from the high-res menus mod into your Override folder." % MAP_GUI)


def check_map_gui(game_dir, width, height):
    """Prove the installed .gui set is the one for the exe's resolution."""
    got = read_map_extent(game_dir)
    want = expected_map_extent(width, height)
    if any(abs(a - b) > GUI_TOLERANCE for a, b in zip(got, want)):
        raise Refusal(
            "Your menu files and your game don't match.\n"
            "\n"
            "Your game is set up for %dx%d, but the menu files in your\n"
            "Override folder were made for a different resolution.\n"
            "\n"
            "This usually means the high-res menus mod was run at one\n"
            "resolution and its menu files were copied from another. Copy the\n"
            "menu file set for %dx%d into your Override folder and run this\n"
            "again.\n"
            "\n"
            "(%s draws the map at %s; at %dx%d it should be %s.)"
            % (width, height, width, height, MAP_GUI, got, width, height, want))
    return got


# --- is our layer already there -----------------------------------------
def _sites():
    """The three marker hook sites, with their before/after bytes."""
    hp = hires_patch
    return [
        ("area-map marker cave", hp.MARKER_HOOK_VA - hp.IMAGE_BASE,
         hp.MARKER_HOOK_DEFAULT, hp.MARKER_HOOK_JMP),
        ("party marker cave", hp.PARTY_HOOK_VA - hp.IMAGE_BASE,
         hp.PARTY_HOOK_DEFAULT, hp.PARTY_HOOK_JMP),
        ("player marker cave", hp.PLAYER_HOOK_VA - hp.IMAGE_BASE,
         hp.PLAYER_HOOK_DEFAULT, hp.PLAYER_HOOK_JMP + hp.PLAYER_HOOK_NOP_PAD),
    ]


def layer_state(data, width, height):
    """'none', 'full' or 'partial' - is OUR layer already applied?

    Deliberately checks every layer independently. A half-applied exe (an
    interrupted run, a partial restore) must never be silently patched again on
    top of itself, and must not be reported as clean.
    """
    import note_table_patch as ntp
    hp = hires_patch

    found = {}

    # 1. mapscale int16 sites: vanilla default vs the value for this resolution
    values = hp.map_scale_values(width, height)
    vanilla = patched = total = 0
    for key, off, tpl, default in scale_sites():
        want = hp._round_half_up(values[key])
        (cur,) = struct.unpack_from(tpl, data, off)
        total += 1
        vanilla += cur == default
        patched += cur == want
    found["mapscale"] = "full" if patched == total else (
        "none" if vanilla == total else "partial")

    # 2. private float copies for the Area Map's tile size
    slots = [struct.unpack_from("<f", data, s)[0]
             for s in hp.PRIVATE_FLOAT_SLOTS.values()]
    operands = [struct.unpack_from("<I", data, o)[0]
                for axis in hp.BIGMAP_FLOAT_OPERANDS
                for o in hp.BIGMAP_FLOAT_OPERANDS[axis]]
    private_ok = all(v != 0.0 for v in slots) and all(
        o - hp.IMAGE_BASE in hp.PRIVATE_FLOAT_SLOTS.values() for o in operands)
    private_none = all(v == 0.0 for v in slots)
    found["private_floats"] = "full" if private_ok else (
        "none" if private_none else "partial")

    # 3. the three marker hooks
    for label, off, default, jmp in _sites():
        cur = bytes(data[off:off + len(default)])
        found[label] = ("none" if cur == default else
                        "full" if cur == jmp else "partial")

    # 4. reserved region and the note-table hook
    found["note table region"] = "full" if pe_space.find_region(data) else "none"
    off = ntp.HOOK_VA - hp.IMAGE_BASE
    cur = bytes(data[off:off + len(ntp.HOOK_DEFAULT)])
    found["note table hook"] = ("none" if cur == ntp.HOOK_DEFAULT else
                                "full" if cur[:1] == b"\xe9" else "partial")

    states = set(found.values())
    overall = "none" if states == {"none"} else (
        "full" if states == {"full"} else "partial")
    return overall, found
