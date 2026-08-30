"""KOTOR 1 area-map calibration: world position <-> map-pixel space.

Shared library for the map-note work. Everything here was derived from the real
exe (VA 0x578E00, the ARE loader at ~0x509c50) and verified against live x32dbg
captures and a real 2560x1600 screenshot - see NOTES.md
"Session 2026-08-28, independent review" and REVIEW-2026-08-28-independent.md.

THE MODEL (verified bit-exact against a live-captured calibration object)
------------------------------------------------------------------------
Per area, the ARE's `Map` struct holds MapPt1/2 (normalised 0..1 fractions of
the map image), WorldPt1/2 (raw world coords), and NorthAxis (0..3).

    MapPt_scaled = round(MapPt_fraction * 440.0)   # X axis
    MapPt_scaled = round(MapPt_fraction * 256.0)   # Y axis   <- the rounding is REAL
    (WX, WY)     = axis_map(NorthAxis, WorldPtN)              # <- easy to miss
    scale        = (WX1 - WX2) / (MapPt_scaled1 - MapPt_scaled2)
    offset       = WX1 - scale * MapPt_scaled1

and the draw-time transform (VA 0x578E00) is

    (X, Y)  = axis_map(NorthAxis, worldX, worldY)
    pixelX  = int((X - offsetX) / scaleX + 0.5)
    pixelY  = int((Y - offsetY) / scaleY + 0.5)
    drawn only if 0 <= pixelX <= 440 and 0 <= pixelY <= 256   (vanilla bounds)

NorthAxis is stored at calibration-object +0x10 and selects an axis
swap/negation BEFORE offset/scale are applied:

    0 -> ( X,  Y)     1 -> (-X, -Y)     2 -> ( Y, -X)     3 -> (-Y,  X)

It cancels out for NorthAxis 0 and 1, which is why omitting it went unnoticed;
it does NOT cancel for 2 and 3 (12 of the 90 note-bearing modules). Model
selection was done by counting how many of the game's 340 map notes survive the
engine's own bound check: omitting NorthAxis entirely rejects 9, applying it
only in the transform rejects 57, applying it in both places rejects 1.

MAP ART
-------
The Area Map background is `lbl_map<areaResRef>` in
TexturePacks/swpc_tex_gui.erf (97 of them). Each is 512x256, of which only the
LEFT 440x256 is drawn - the rest is power-of-two padding. TPC data is stored
BOTTOM-UP, so it must be flipped vertically before sampling. Verified against a
real screenshot: predicted art bbox matched the rendered art to ~1-3 px.

The patched game scales both the art and the markers by the same kx = width/640
and ky = height/480, so map-pixel space (0..440 x 0..256) is resolution
independent. Work in that space; it is correct at every resolution.
"""

from __future__ import annotations

import os
import glob

from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.erf import read_erf
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.formats.tpc import read_tpc, TPCTextureFormat
from pykotor.resource.type import ResourceType

DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

MAP_W = 440.0   # .rdata 0x747748, left untouched by our patches
MAP_H = 256.0   # .rdata 0x7455d4

# Lists in a .git whose structs carry a position, with the field names they use.
# Doors are the odd one out: they store X/Y/Z, not XPosition/YPosition/ZPosition.
# (Reading them as XPosition silently dropped every door in the game from the
# object lists - found 2026-08-28.)
POSITIONED_LISTS = [
    ("WaypointList", "XPosition", "YPosition"),
    ("TriggerList", "XPosition", "YPosition"),
    ("SoundList", "XPosition", "YPosition"),
    ("Placeable List", "XPosition", "YPosition"),
    ("Creature List", "XPosition", "YPosition"),
    ("Door List", "X", "Y"),
]


# --------------------------------------------------------------------------
# NorthAxis
# --------------------------------------------------------------------------
def axis_map(north_axis, x, y):
    """Forward axis mapping applied by 0x578E00 before offset/scale."""
    if north_axis == 1:
        return -x, -y
    if north_axis == 2:
        return y, -x
    if north_axis == 3:
        return -y, x
    return x, y


def axis_unmap(north_axis, X, Y):
    """Inverse of axis_map - needed to turn a chosen map pixel back into a
    world position when authoring a correction."""
    if north_axis == 1:
        return -X, -Y
    if north_axis == 2:
        return -Y, X
    if north_axis == 3:
        return Y, -X
    return X, Y


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------
class Calibration:
    """Per-area world <-> map-pixel calibration, in VANILLA 440x256 space."""

    __slots__ = ("area", "north_axis", "scale_x", "scale_y",
                 "offset_x", "offset_y", "raw")

    def __init__(self, area, north_axis, sx, sy, ox, oy, raw):
        self.area = area
        self.north_axis = north_axis
        self.scale_x, self.scale_y = sx, sy
        self.offset_x, self.offset_y = ox, oy
        self.raw = raw

    def to_pixel(self, wx, wy, integer=True):
        """world -> map pixel. Mirrors 0x578E00 including its +0.5/truncate."""
        X, Y = axis_map(self.north_axis, wx, wy)
        px = (X - self.offset_x) / self.scale_x
        py = (Y - self.offset_y) / self.scale_y
        if integer:
            return int(px + 0.5), int(py + 0.5)
        return px, py

    def to_world(self, px, py):
        """map pixel -> world. Inverse of to_pixel; Z is the caller's problem."""
        X = px * self.scale_x + self.offset_x
        Y = py * self.scale_y + self.offset_y
        return axis_unmap(self.north_axis, X, Y)

    def in_bounds(self, px, py):
        """Does the engine actually draw a marker at this pixel?"""
        return 0 <= px <= MAP_W and 0 <= py <= MAP_H

    def __repr__(self):
        return ("Calibration(area=%s, NorthAxis=%d, scale=(%.8f, %.8f), "
                "offset=(%.6f, %.6f))" % (self.area, self.north_axis,
                                          self.scale_x, self.scale_y,
                                          self.offset_x, self.offset_y))


def calibration_from_are(area_gff, area_resref):
    """Build a Calibration from an already-parsed .are GFF. None if the area
    has no usable map data (missing fields, or a degenerate MapPt pair)."""
    m = area_gff.root.acquire("Map", None)
    if m is None:
        return None
    v = {label: value for label, _ftype, value in m}
    need = ("MapPt1X", "MapPt2X", "MapPt1Y", "MapPt2Y",
            "WorldPt1X", "WorldPt2X", "WorldPt1Y", "WorldPt2Y")
    if any(k not in v for k in need):
        return None

    nx = v.get("NorthAxis", 0)
    m1x, m2x = round(v["MapPt1X"] * MAP_W), round(v["MapPt2X"] * MAP_W)
    m1y, m2y = round(v["MapPt1Y"] * MAP_H), round(v["MapPt2Y"] * MAP_H)
    if m1x == m2x or m1y == m2y:
        return None  # degenerate: the engine would divide by zero here too

    w1x, w1y = axis_map(nx, v["WorldPt1X"], v["WorldPt1Y"])
    w2x, w2y = axis_map(nx, v["WorldPt2X"], v["WorldPt2Y"])
    sx = (w1x - w2x) / (m1x - m2x)
    sy = (w1y - w2y) / (m1y - m2y)
    return Calibration(area_resref, nx, sx, sy,
                       w1x - sx * m1x, w1y - sy * m1y, v)


# --------------------------------------------------------------------------
# Module loading
# --------------------------------------------------------------------------
class Module:
    """One module's .are + .git, with its calibration and object lists."""

    def __init__(self, name, area_resref, calibration, notes, objects,
                 transitions=None, objects_full=None, area_name=""):
        self.name = name
        self.area = area_resref
        # The area's own display name, from the .are `Name` strref. Needed to
        # label a map for a human ("Taris - Upper City South"), since a resref
        # like `m02ac` is not something you can recognise on sight.
        self.area_name = area_name
        self.calibration = calibration
        self.notes = notes          # list of MapNote
        self.objects = objects      # list of (list_name, tag, wx, wy)
        self.transitions = transitions or []   # list of Transition
        # As `objects`, plus each object's TemplateResRef, which is how its
        # display name is looked up. `objects` keeps its 4-tuple shape because
        # map_note_survey.py unpacks it positionally.
        self.objects_full = objects_full or []


class Transition:
    """A door or trigger that moves the player somewhere else.

    These are what "To the Undercity" / "Exit" style map notes actually name, so
    they are exact ground truth for that whole class of note. `dest_strref` is
    the TransitionDestin string (the destination's own name in dialog.tlk);
    `linked_module` is the module it leads to.
    """

    __slots__ = ("kind", "index", "tag", "template", "dest_strref",
                 "linked_module", "linked_to", "x", "y")

    def __init__(self, kind, index, tag, template, dest_strref,
                 linked_module, linked_to, x, y):
        self.kind = kind            # "trigger" | "door"
        self.index = index
        self.tag = tag
        self.template = template
        self.dest_strref = dest_strref
        self.linked_module = linked_module
        self.linked_to = linked_to
        self.x, self.y = x, y       # trigger: its Geometry centroid, not its origin

    def __repr__(self):
        return "Transition(%s %s -> %s at (%.2f,%.2f))" % (
            self.kind, self.tag, self.linked_module or "?", self.x, self.y)


def _transitions_from_git(git_gff):
    """Every door/trigger in a .git that carries a transition. A trigger's
    anchor is the centroid of its Geometry polygon (points are local to the
    trigger's own position), which is a better answer than its origin corner."""
    out = []
    for list_name, kind, xf, yf in (("TriggerList", "trigger", "XPosition", "YPosition"),
                                    ("Door List", "door", "X", "Y")):
        lst = git_gff.root.acquire(list_name, None)
        if lst is None:
            continue
        for i in range(len(lst)):
            st = lst.at(i)
            linked = str(st.acquire("LinkedToModule", "") or "")
            dest = st.acquire("TransitionDestin", None)
            dest_strref = getattr(dest, "stringref", -1) if dest is not None else -1
            if not linked and dest_strref < 0:
                continue
            x, y = st.acquire(xf, None), st.acquire(yf, None)
            if x is None or y is None:
                continue
            x, y = float(x), float(y)
            geom = st.acquire("Geometry", None)
            if geom is not None and len(geom):
                gx = gy = 0.0
                for g in range(len(geom)):
                    gs = geom.at(g)
                    gx += float(gs.acquire("PointX", 0.0) or 0.0)
                    gy += float(gs.acquire("PointY", 0.0) or 0.0)
                x += gx / len(geom)
                y += gy / len(geom)
            out.append(Transition(
                kind, i, str(st.acquire("Tag", "") or ""),
                str(st.acquire("TemplateResRef", "") or ""),
                dest_strref, linked, str(st.acquire("LinkedTo", "") or ""), x, y))
    return out


class MapNote:
    __slots__ = ("index", "tag", "template", "strref", "x", "y", "z")

    def __init__(self, index, tag, template, strref, x, y, z):
        self.index, self.tag, self.template = index, tag, template
        self.strref = strref
        self.x, self.y, self.z = x, y, z


def load_module(rim_path):
    """Read one module .rim. Returns a Module, or None if it has no map data."""
    try:
        rim = read_rim(rim_path)
    except Exception:
        return None
    are = git = area_resref = None
    for res in rim:
        if res.restype == ResourceType.ARE:
            are, area_resref = res.data, str(res.resref)
        elif res.restype == ResourceType.GIT:
            git = res.data
    if are is None or git is None:
        return None
    try:
        area_gff = read_gff(are)
        git_gff = read_gff(git)
    except Exception:
        return None

    cal = calibration_from_are(area_gff, area_resref)
    if cal is None:
        return None

    notes, objects, objects_full = [], [], []
    for list_name, xfield, yfield in POSITIONED_LISTS:
        lst = git_gff.root.acquire(list_name, None)
        if lst is None:
            continue
        for i in range(len(lst)):
            st = lst.at(i)
            x = st.acquire(xfield, None)
            y = st.acquire(yfield, None)
            if x is None or y is None:
                continue
            tag = str(st.acquire("Tag", "") or "")
            # HasMapNote - NOT MapNoteEnabled - is what makes a note render.
            # In ebo_m12aa 33 waypoints have MapNoteEnabled=1 but only the 7
            # with HasMapNote=1 are drawn.
            if list_name == "WaypointList" and st.acquire("HasMapNote", 0):
                mn = st.acquire("MapNote", None)
                notes.append(MapNote(
                    i, tag, str(st.acquire("TemplateResRef", "") or ""),
                    getattr(mn, "stringref", -1) if mn is not None else -1,
                    float(x), float(y), float(st.acquire("ZPosition", 0.0) or 0.0)))
            else:
                objects.append((list_name, tag, float(x), float(y)))
                objects_full.append((
                    list_name, tag,
                    str(st.acquire("TemplateResRef", "") or ""),
                    float(x), float(y)))

    area_name = ""
    nm = area_gff.root.acquire("Name", None)
    ref = getattr(nm, "stringref", -1)
    if ref is not None and ref >= 0:
        area_name = strref_text(ref, os.path.dirname(os.path.dirname(rim_path)))

    name = os.path.basename(rim_path)
    return Module(name[:-4] if name.endswith(".rim") else name,
                  area_resref, cal, notes, objects,
                  _transitions_from_git(git_gff), objects_full, area_name)


def iter_modules(game_dir=DEFAULT_GAME):
    """Yield a Module for every base module .rim (skipping `_s` companions)."""
    pattern = os.path.join(game_dir, "modules", "*.rim")
    for path in sorted(glob.glob(pattern)):
        if os.path.basename(path).endswith("_s.rim"):
            continue
        mod = load_module(path)
        if mod is not None:
            yield mod


# --------------------------------------------------------------------------
# Map art
# --------------------------------------------------------------------------
_tex_erf = None
_tex_cache = {}


def load_map_texture(area_resref, game_dir=DEFAULT_GAME):
    """Return the 440x256 map background for an area as a PIL RGB image,
    already flipped to screen orientation and cropped to the drawn region.
    Returns None if the area has no map texture."""
    from PIL import Image

    global _tex_erf
    if _tex_erf is None:
        erf = read_erf(os.path.join(game_dir, "TexturePacks", "swpc_tex_gui.erf"))
        _tex_erf = {str(r.resref).lower(): r for r in erf
                    if str(r.resref).lower().startswith("lbl_map")}

    key = "lbl_map" + area_resref.lower()
    if key in _tex_cache:
        return _tex_cache[key]
    res = _tex_erf.get(key)
    img = None
    if res is not None:
        tpc = read_tpc(res.data)
        tpc.convert(TPCTextureFormat.RGBA)
        w, h = tpc.dimensions()
        img = (Image.frombytes("RGBA", (w, h), bytes(tpc.get(0, 0).data))
               .convert("RGB")
               .transpose(Image.FLIP_TOP_BOTTOM))       # TPC is bottom-up
        img = img.crop((0, 0, min(int(MAP_W), w), min(int(MAP_H), h)))
    _tex_cache[key] = img
    return img


# --------------------------------------------------------------------------
# dialog.tlk - so a human reviewing 340 notes can see real names
# --------------------------------------------------------------------------
_tlk = None


def strref_text(strref, game_dir=DEFAULT_GAME):
    """Resolve a strref to its dialog.tlk string ('' if unavailable)."""
    global _tlk
    if strref is None or strref < 0:
        return ""
    if _tlk is None:
        try:
            from pykotor.resource.formats.tlk import read_tlk
            _tlk = read_tlk(os.path.join(game_dir, "dialog.tlk"))
        except Exception:
            _tlk = False
    if not _tlk:
        return ""
    try:
        return (_tlk.get(strref).text or "").strip()
    except Exception:
        return ""


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: tools/map_calibration.py <module_name> [game_dir]")
        print("  dumps one module's calibration and its map notes")
        raise SystemExit(2)
    game = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_GAME
    mod = load_module(os.path.join(game, "modules", sys.argv[1] + ".rim"))
    if mod is None:
        print("no map data for", sys.argv[1])
        raise SystemExit(1)
    cal = mod.calibration
    print(cal)
    print("raw Map struct:", {k: mod.calibration.raw[k] for k in sorted(cal.raw)})
    print("\n%-3s %-18s %-8s %-24s %-14s %s"
          % ("#", "tag", "strref", "name", "world", "map px"))
    for n in mod.notes:
        px = cal.to_pixel(n.x, n.y)
        print("%-3d %-18s %-8s %-24s (%7.2f,%7.2f) (%3d,%3d)%s"
              % (n.index, n.tag, n.strref, strref_text(n.strref, game)[:24],
                 n.x, n.y, px[0], px[1],
                 "" if cal.in_bounds(*px) else "  <== OUT OF BOUNDS, never drawn"))
