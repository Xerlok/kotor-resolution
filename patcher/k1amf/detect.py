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
            raise Refusal("no swkotor.exe in %s" % explicit)
        return explicit
    for cand in candidate_game_dirs(start):
        if os.path.isfile(os.path.join(cand, "swkotor.exe")):
            return cand
    raise Refusal(
        "could not find your KOTOR install.\n"
        "Run the patcher again with the folder that holds swkotor.exe:\n"
        '    Apply.bat "C:\\Path\\To\\swkotor"')


# --- is this the build we know ------------------------------------------
def check_build(data, exe_path):
    if len(data) == PATCHED_SIZE and pe_space.find_region(data):
        return          # already ours; layer_state() reports it properly
    if len(data) != BASE_SIZE:
        raise Refusal(
            "%s is %d bytes; this patcher only knows the %d-byte "
            '"Editable Executable" that UniWS and KotOR High Resolution Menus '
            "are made for.\n"
            "If you are on the Steam release, swap in the Editable Executable "
            "first (it ships with the game as swkotor.exe in the game folder "
            "after running the UniWS patcher). The GOG and 4-CD builds are "
            "untested and will be refused here rather than guessed at."
            % (os.path.basename(exe_path), len(data), BASE_SIZE))


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
            "this exe still has the vanilla 640x480 canvas constants, which "
            "means KotOR High Resolution Menus (k1hrm) has not been run on it.\n"
            "Install order:\n"
            "  1. UniWS  - unlocks the resolution\n"
            "  2. KotOR High Resolution Menus (k1hrm) - rebuilds the menus at "
            "that resolution\n"
            "  3. this patcher\n"
            "Both are required; this mod fixes the Area Map on top of them and "
            "does not replace either.")

    if len(set(xs)) != 1 or len(set(ys)) != 1:
        raise Refusal(
            "this exe is only half-patched: the canvas constants disagree "
            "(width %s, height %s).\n"
            "Restore a clean Editable Executable and run UniWS and k1hrm again "
            "before this patcher." % (xs, ys))

    width, height = xs[0], ys[0]
    if not (MIN_W <= width <= MAX_W and MIN_H <= height <= MAX_H):
        raise Refusal(
            "the resolution read out of the exe (%dx%d) is not plausible, so "
            "something other than k1hrm has edited these bytes. Refusing to "
            "patch." % (width, height))
    return width, height


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
            "%s is missing.\n"
            "KotOR High Resolution Menus installs it, along with the rest of "
            "the .gui set for your resolution. Run k1hrm before this patcher."
            % MAP_GUI)
    g = gff.load(path)

    def val(v):
        return v.value if hasattr(v, "value") else v

    for c in val(g.top.fields.get("CONTROLS")) or []:
        if val(c.fields.get("TAG")) == "LBL_Map":
            ef = val(c.fields["EXTENT"]).fields
            return tuple(int(val(ef[k])) for k in ("LEFT", "TOP", "WIDTH", "HEIGHT"))
    raise Refusal("%s has no LBL_Map control - it is not a KOTOR map screen."
                  % MAP_GUI)


def check_map_gui(game_dir, width, height):
    """Prove the installed .gui set is the one for the exe's resolution."""
    got = read_map_extent(game_dir)
    want = expected_map_extent(width, height)
    if any(abs(a - b) > GUI_TOLERANCE for a, b in zip(got, want)):
        raise Refusal(
            "the exe is patched for %dx%d, but %s draws the map at %s instead "
            "of %s.\n"
            "That means the .gui files in Override/ are from a different "
            "resolution than the exe. Re-run KotOR High Resolution Menus and "
            "pick the same resolution you patched the exe with."
            % (width, height, MAP_GUI, got, want))
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
