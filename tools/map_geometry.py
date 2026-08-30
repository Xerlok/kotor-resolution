"""Per-room walkable geometry for a KOTOR 1 area, in world coordinates.

Companion to `map_calibration.py`. That module answers "where on the map does
this world position draw?"; this one answers "what is actually THERE?" - which
room, is it walkable floor, and where is that room's centre.

Built for the automated map-note proposal pass (see AREA-MAP-NOTE-FIX-PLAN.md
Phase 2): the point of it is to derive corrected note positions from the game's
own geometry instead of hand-placing 340 notes.

WHAT WAS FOUND (verified 2026-08-28, don't re-derive)
----------------------------------------------------
- An area's room list is `<areaResRef>.lyt` in `data/layouts.bif` (124 of them),
  a plain-text MAXLAYOUT file: `roomcount N` then `<roomModel> x y z` per room.
- Each room's walkmesh is `<roomModel>.wok` in `data/models.bif` (1202 of them).
- **The `.wok` vertices are ALREADY IN WORLD COORDINATES.** The x/y/z on the
  `.lyt` room line must NOT be added - doing so throws rooms hundreds of map
  pixels off the map. (The `.wok` header also carries a `position`, likewise not
  to be added.) Confirmed on `m12aa`: raw room bboxes bracket the module's own
  map-note world positions exactly, offsets applied do not.
- Some rooms have an empty `.wok` (exterior hull shells, e.g. `M12aa_01a`) or no
  walkable faces at all. Skip them; they are not places.

`models.bif` is ~954 MB, so resources are read by seeking into a cached
resource table - never by slurping the file (which is what
`keybif.extract_resource` does; fine for `layouts.bif`, not for this).
"""

from __future__ import annotations

import os
import struct

import keybif

RESTYPE_LYT = 3000
RESTYPE_WOK = 2016


# --------------------------------------------------------------------------
# KEY/BIF access that does not read a 954 MB file per resource
# --------------------------------------------------------------------------
class GameResources:
    """Random-access reader over chitin.key + data/*.bif, with cached tables."""

    def __init__(self, game_dir):
        self.game_dir = game_dir
        key = keybif.read_key(os.path.join(game_dir, "chitin.key"))
        self._bif_names = [b.filename.strip().strip("\x00").replace("\\", os.sep)
                           for b in key.bif_files]
        self._index = {}
        for e in key.entries:
            self._index.setdefault((e.resref.lower(), e.res_type),
                                   (e.bif_index, e.resource_index))
        self._tables = {}     # bif_index -> [(offset, size)]
        self._handles = {}    # bif_index -> open file object

    def _table(self, bif_index):
        if bif_index not in self._tables:
            path = os.path.join(self.game_dir, self._bif_names[bif_index])
            fh = open(path, "rb")
            self._handles[bif_index] = fh
            head = fh.read(20)
            if head[:4] != b"BIFF":
                raise ValueError("not a BIF: %s" % path)
            var_count, _fixed, table_off = struct.unpack_from("<III", head, 8)
            fh.seek(table_off)
            raw = fh.read(var_count * 16)
            self._tables[bif_index] = [
                struct.unpack_from("<IIII", raw, i * 16)[1:3] for i in range(var_count)
            ]
        return self._tables[bif_index]

    def fetch(self, resref, restype):
        """Raw bytes for one resource, or None if the game does not have it."""
        hit = self._index.get((resref.lower(), restype))
        if hit is None:
            return None
        bif_index, res_index = hit
        table = self._table(bif_index)
        if res_index >= len(table):
            return None
        offset, size = table[res_index]
        fh = self._handles[bif_index]
        fh.seek(offset)
        return fh.read(size)

    def close(self):
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()


# --------------------------------------------------------------------------
# 2D helpers (map notes only ever care about XY; the transform ignores Z)
# --------------------------------------------------------------------------
def _point_in_tri(px, py, t):
    (ax, ay), (bx, by), (cx, cy) = t
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if d == 0.0:
        return False
    a = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
    b = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
    return a >= 0.0 and b >= 0.0 and (a + b) <= 1.0


def _closest_on_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0.0:
        return ax, ay
    t = ((px - ax) * dx + (py - ay) * dy) / L
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return ax + t * dx, ay + t * dy


def _closest_on_tri(px, py, t):
    """Closest point of a triangle to (px,py), and whether the point is inside."""
    if _point_in_tri(px, py, t):
        return px, py, 0.0
    best = None
    for i in range(3):
        ax, ay = t[i]
        bx, by = t[(i + 1) % 3]
        qx, qy = _closest_on_segment(px, py, ax, ay, bx, by)
        d = (qx - px) ** 2 + (qy - py) ** 2
        if best is None or d < best[2]:
            best = (qx, qy, d)
    return best[0], best[1], best[2] ** 0.5


def _tri_area(t):
    (ax, ay), (bx, by), (cx, cy) = t
    return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2.0


# --------------------------------------------------------------------------
class Room:
    """One room's walkable floor, as world-space triangles."""

    __slots__ = ("name", "tris", "area", "cx", "cy", "x0", "y0", "x1", "y1")

    def __init__(self, name, tris):
        self.name = name
        self.tris = tris
        a = cx = cy = 0.0
        for t in tris:
            ta = _tri_area(t)
            a += ta
            cx += ta * (t[0][0] + t[1][0] + t[2][0]) / 3.0
            cy += ta * (t[0][1] + t[1][1] + t[2][1]) / 3.0
        self.area = a
        # Area-weighted centroid. It can fall in a hole for an L-shaped or
        # ring-shaped room, so callers that need a point ON the floor should
        # pass it through nearest_floor_point().
        self.cx = cx / a if a else 0.0
        self.cy = cy / a if a else 0.0
        xs = [p[0] for t in tris for p in t]
        ys = [p[1] for t in tris for p in t]
        self.x0, self.x1 = min(xs), max(xs)
        self.y0, self.y1 = min(ys), max(ys)

    def contains(self, x, y):
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            return False
        return any(_point_in_tri(x, y, t) for t in self.tris)

    def distance(self, x, y):
        """0.0 if (x,y) is on this room's floor, else world distance to it."""
        best = float("inf")
        for t in self.tris:
            _qx, _qy, d = _closest_on_tri(x, y, t)
            if d < best:
                best = d
                if best == 0.0:
                    break
        return best

    def nearest_floor_point(self, x, y):
        """Closest point on this room's walkable floor to (x,y)."""
        best = None
        for t in self.tris:
            qx, qy, d = _closest_on_tri(x, y, t)
            if best is None or d < best[2]:
                best = (qx, qy, d)
                if d == 0.0:
                    break
        return best[0], best[1]

    def centroid_on_floor(self):
        """The room centre, pulled onto actual floor if the centroid lands in a
        hole (ring-shaped rooms - the Ebon Hawk's main hold is one)."""
        if self.contains(self.cx, self.cy):
            return self.cx, self.cy
        return self.nearest_floor_point(self.cx, self.cy)

    def __repr__(self):
        return "Room(%s, area=%.1f, centre=(%.2f,%.2f))" % (
            self.name, self.area, self.cx, self.cy)


class AreaGeometry:
    """All walkable rooms of one area, in world coordinates."""

    def __init__(self, area_resref, rooms):
        self.area = area_resref
        self.rooms = rooms

    def room_at(self, x, y):
        """The room whose floor covers (x,y); on overlap the smaller room wins
        (a doorway triangle shared with a big hall should read as the room)."""
        hits = [r for r in self.rooms if r.contains(x, y)]
        if not hits:
            return None
        return min(hits, key=lambda r: r.area)

    def nearest_room(self, x, y):
        """(room, world distance) for the closest room floor. (None, inf) if
        the area has no walkable geometry at all."""
        best, best_d = None, float("inf")
        for r in self.rooms:
            d = r.distance(x, y)
            if d < best_d:
                best, best_d = r, d
                if best_d == 0.0:
                    break
        return best, best_d

    def on_floor(self, x, y):
        return self.room_at(x, y) is not None


# --------------------------------------------------------------------------
_geom_cache = {}


def load_area_geometry(area_resref, resources):
    """Rooms of one area from its .lyt + per-room .wok. None if the area has no
    layout (a few do not). Cached - safe to call per note."""
    key = area_resref.lower()
    if key in _geom_cache:
        return _geom_cache[key]

    lyt = resources.fetch(area_resref, RESTYPE_LYT)
    if lyt is None:
        _geom_cache[key] = None
        return None

    lines = [l.strip() for l in lyt.decode("ascii", "replace").splitlines()]
    room_names = []
    for i, line in enumerate(lines):
        if line.lower().startswith("roomcount"):
            try:
                n = int(line.split()[1])
            except (IndexError, ValueError):
                break
            for j in range(1, n + 1):
                if i + j < len(lines) and lines[i + j]:
                    room_names.append(lines[i + j].split()[0])
            break

    from pykotor.resource.formats.bwm import read_bwm

    rooms = []
    for name in room_names:
        data = resources.fetch(name, RESTYPE_WOK)
        if not data:
            continue
        try:
            bwm = read_bwm(data)
        except Exception:
            continue
        tris = []
        for f in bwm.faces:
            try:
                walkable = f.material.walkable()
            except TypeError:
                walkable = bool(f.material.walkable)
            if not walkable:
                continue
            # .wok vertices are already world-space - no .lyt offset. See docstring.
            tris.append(((f.v1.x, f.v1.y), (f.v2.x, f.v2.y), (f.v3.x, f.v3.y)))
        if tris:
            room = Room(name, tris)
            if room.area > 0.0:
                rooms.append(room)

    geom = AreaGeometry(area_resref, rooms) if rooms else None
    _geom_cache[key] = geom
    return geom


if __name__ == "__main__":
    import sys
    import map_calibration as mc

    if len(sys.argv) < 2:
        print("usage: tools/map_geometry.py <module_name> [game_dir]")
        print("  dumps one module's rooms, in map-pixel space, next to its notes")
        raise SystemExit(2)
    game = sys.argv[2] if len(sys.argv) > 2 else mc.DEFAULT_GAME
    mod = mc.load_module(os.path.join(game, "modules", sys.argv[1] + ".rim"))
    if mod is None:
        print("no map data for", sys.argv[1])
        raise SystemExit(1)
    res = GameResources(game)
    geom = load_area_geometry(mod.area, res)
    if geom is None:
        print("no room geometry for area", mod.area)
        raise SystemExit(1)
    cal = mod.calibration
    print("%s: %d walkable rooms" % (mod.area, len(geom.rooms)))
    print("%-16s %6s %6s  %-12s %s" % ("room", "tris", "area", "centre px", "bbox px"))
    for r in sorted(geom.rooms, key=lambda r: -r.area):
        c = cal.to_pixel(*r.centroid_on_floor())
        lo = cal.to_pixel(r.x0, r.y0)
        hi = cal.to_pixel(r.x1, r.y1)
        print("%-16s %6d %6.1f  (%3d,%3d)     x%3d..%-3d y%3d..%-3d"
              % (r.name, len(r.tris), r.area, c[0], c[1],
                 min(lo[0], hi[0]), max(lo[0], hi[0]),
                 min(lo[1], hi[1]), max(lo[1], hi[1])))
    print()
    for n in mod.notes:
        px = cal.to_pixel(n.x, n.y)
        room = geom.room_at(n.x, n.y)
        near, d = geom.nearest_room(n.x, n.y)
        print("note #%-3d %-16s %-24s px(%3d,%3d)  room=%s%s"
              % (n.index, n.tag, mc.strref_text(n.strref, game), px[0], px[1],
                 room.name if room else "OFF-FLOOR",
                 "" if room else " (nearest %s at %.2f world)" % (near.name, d)))
