"""Door and area-transition marker lines, read out of the map artwork.

KOTOR's area-map textures mark a door with a short GREEN segment and an
area transition with a short BLUE segment. Those segments are what the player
actually looks at, so for a note that names a way through, the right anchor is
the segment itself: **centred along the line, just before it on the approach
side** (user's specification, 2026-08-28, after seeing the first patched build).

This matters because a transition OBJECT's position is not centred on its drawn
line. Measured on `m12aa`: the blue segment occupies x 268..281, y 96..97 -
centre x 274.5 - while the `AreaTransition` trigger's geometry centroid projects
to x 272. Vanilla had the "Exit Ramp" note at x 274, i.e. BioWare centred it on
the line and the object-based snap moved it 2.5 px off.

Detection is relative, not against fixed RGB values, so it survives the
different palettes across areas: a pixel counts as green if G clearly dominates
both R and B, blue if B clearly dominates both R and G. Verified to find
segments in m12aa (28 blue px, 1 segment), m13aa (208 green, 29 blue),
m02ac (85/86), m26ae (214/61), m17aa (0/136).
"""

from __future__ import annotations

import map_calibration as mc

MIN_CHANNEL = 90        # a marker pixel is brightly coloured
MIN_DOMINANCE = 40      # ...and its channel clearly dominates the other two
MIN_CLUSTER = 3         # ignore stray blended pixels
MIN_BBOX_FILL = 0.25    # below this the segment is a diagonal streak, not a line
MAX_THICKNESS = 8       # a marker segment is thin; anything fatter is artwork


AXIS_ALIGNED_DOT = 0.966   # within ~15 deg of x or y counts as axis-aligned
PCA_MAX_CROSS = 2.5        # a real segment is thin ACROSS its principal axis
PCA_MIN_RATIO = 2.0        # ...and clearly longer along it than across


class Line:
    """One drawn marker segment, in vanilla map-pixel space."""

    __slots__ = ("kind", "pixels", "x0", "y0", "x1", "y1", "cx", "cy", "horizontal",
                 "_pca")

    def __init__(self, kind, pixels):
        self.kind = kind                      # "door" | "transition"
        self.pixels = pixels
        self._pca = None
        xs = [p[0] for p in pixels]
        ys = [p[1] for p in pixels]
        self.x0, self.x1 = min(xs), max(xs)
        self.y0, self.y1 = min(ys), max(ys)
        self.cx = (self.x0 + self.x1) / 2.0
        self.cy = (self.y0 + self.y1) / 2.0
        self.horizontal = (self.x1 - self.x0) >= (self.y1 - self.y0)

    def length(self):
        return max(self.x1 - self.x0, self.y1 - self.y0) + 1

    def distance(self, px, py):
        """Distance from a map pixel to this segment's bounding box."""
        dx = max(self.x0 - px, 0, px - self.x1)
        dy = max(self.y0 - py, 0, py - self.y1)
        return (dx * dx + dy * dy) ** 0.5

    def side_of(self, px, py):
        """Which side of the line a map pixel is on: +1 or -1."""
        if self.horizontal:
            return 1.0 if py >= self.cy else -1.0
        return 1.0 if px >= self.cx else -1.0

    def anchor(self, from_px=None, from_py=None, gap=3.0, side=None, along=None):
        """Where a note pointing at this line belongs: offset `gap` px clear of
        the line on the approach side, and centred **along** it.

        A line tells you two separate things and only one is always reliable:

          - PERPENDICULAR to the line: where the boundary is. Always usable.
          - ALONG the line: where the way through is - but only for a SHORT
            marker segment, i.e. a discrete doorway. Some maps draw a long blue
            strip down a whole wall (kas_m23ac: 45 px long, 8 px thick), and the
            actual door sits at one END of it, so the strip's midpoint is
            meaningless. Callers pass `along` (from the door object's own
            position) for those; see LINE_CENTRE_MAX_LEN in map_note_propose.

        The approach side defaults to the side the note currently sits on, which
        preserves which side of the door BioWare meant; for a door between two
        walkable rooms nothing else can tell us. Pass `side` (+1/-1) to force it.

        Returned coordinates are snapped to whole map pixels: the engine draws at
        `int(px + 0.5)`, so a fractional anchor (a line centre of 274.5) sits
        exactly on the rounding boundary and float32 noise decides which pixel
        it lands on.
        """
        if side is None:
            side = self.side_of(from_px, from_py)
        if self.horizontal:
            edge = self.y1 if side > 0 else self.y0
            ax = self.cx if along is None else along
            return float(int(ax + 0.5)), float(int(edge + side * gap + 0.5))
        edge = self.x1 if side > 0 else self.x0
        ay = self.cy if along is None else along
        return float(int(edge + side * gap + 0.5)), float(int(ay + 0.5))

    def thickness(self):
        return min(self.x1 - self.x0, self.y1 - self.y0) + 1

    def fill(self):
        """Fraction of the bounding box the segment actually covers."""
        w = self.x1 - self.x0 + 1
        h = self.y1 - self.y0 + 1
        return len(self.pixels) / float(w * h)

    # ----------------------------------------------------------------------
    # True orientation, from the pixels themselves rather than the bbox.
    #
    # A bounding box describes a diagonal segment badly: tar_m02af's transition
    # streak is a 33x31 box at 0.12 fill, so "which side of it" cannot be said
    # as +/-x or +/-y, and the old code rejected such segments outright (open
    # item 5). The principal axis of the pixel cloud gives the real direction,
    # its perpendicular gives the real offset direction, and the same code then
    # handles axis-aligned and diagonal segments alike.
    # ----------------------------------------------------------------------
    def _geom(self):
        """(centre, unit axis, unit normal, spread along axis, spread across)."""
        if self._pca is None:
            pts = self.pixels
            n = float(len(pts))
            mx = sum(p[0] for p in pts) / n
            my = sum(p[1] for p in pts) / n
            sxx = sum((p[0] - mx) ** 2 for p in pts) / n
            syy = sum((p[1] - my) ** 2 for p in pts) / n
            sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
            # eigenvalues of the 2x2 covariance matrix
            tr, det = sxx + syy, sxx * syy - sxy * sxy
            disc = max(tr * tr / 4.0 - det, 0.0) ** 0.5
            l1, l2 = tr / 2.0 + disc, max(tr / 2.0 - disc, 0.0)
            if abs(sxy) > 1e-9:
                vx, vy = l1 - syy, sxy
            else:
                vx, vy = (1.0, 0.0) if sxx >= syy else (0.0, 1.0)
            norm = (vx * vx + vy * vy) ** 0.5 or 1.0
            ax, ay = vx / norm, vy / norm
            self._pca = ((mx, my), (ax, ay), (-ay, ax), l1 ** 0.5, l2 ** 0.5)
        return self._pca

    def is_axis_aligned(self):
        (_c, (ax, ay), _n, _s1, _s2) = self._geom()
        return max(abs(ax), abs(ay)) >= AXIS_ALIGNED_DOT

    def _projections(self):
        (mx, my), (ax, ay), (nx, ny), _s1, _s2 = self._geom()
        along = [(p[0] - mx) * ax + (p[1] - my) * ay for p in self.pixels]
        across = [(p[0] - mx) * nx + (p[1] - my) * ny for p in self.pixels]
        return along, across

    def axis_length(self):
        """Length along the true principal axis, in map pixels."""
        along, _across = self._projections()
        return max(along) - min(along) + 1.0

    def thin_and_long(self):
        """Is this a genuine thin segment when measured along its true axis?"""
        _c, _a, _n, s1, s2 = self._geom()
        return s2 <= PCA_MAX_CROSS and s1 >= PCA_MIN_RATIO * max(s2, 0.35)

    def perp_offset(self, px, py):
        """Signed distance from the segment's axis, along its normal."""
        (mx, my), _a, (nx, ny), _s1, _s2 = self._geom()
        return (px - mx) * nx + (py - my) * ny

    def side_of_normal(self, px, py):
        return 1.0 if self.perp_offset(px, py) >= 0.0 else -1.0

    def anchor_normal(self, gap=3.0, side=1.0, along_seed=None):
        """Anchor for a segment of any orientation: centred along its principal
        axis and `gap` px clear of its edge along the true normal.

        The along-axis position defaults to the segment's own centre; pass
        `along_seed` (a map pixel, e.g. the door object's position) for a long
        strip whose midpoint means nothing - same rule as `anchor()`.
        """
        (mx, my), (ax, ay), (nx, ny), _s1, _s2 = self._geom()
        _along, across = self._projections()
        half = max(abs(min(across)), abs(max(across)))
        t = 0.0
        if along_seed is not None:
            t = (along_seed[0] - mx) * ax + (along_seed[1] - my) * ay
        out = half + gap
        px = mx + ax * t + nx * side * out
        py = my + ay * t + ny * side * out
        # whole map pixels: the engine draws at int(px + 0.5), so a fractional
        # anchor sits on the rounding boundary (see anchor()).
        return float(int(px + 0.5)), float(int(py + 0.5))

    def usable_as_anchor(self):
        """Whether an axis-aligned offset from this segment is meaningful.

        A DIAGONAL streak has a big square bounding box that it barely fills, so
        "offset perpendicular to it" cannot be expressed as +/- x or +/- y and
        the result lands in open floor. Measured: tar_m02af's diagonal
        transition streak is a 33x31 box at 0.12 fill, while every genuine
        axis-aligned marker fills 0.27-1.00 (m12aa 14x2 at 1.00, m23ac 8x45 at
        0.33, m40ab's doors 18x4 at 0.82). Compact little path-end markers
        (7x7 at 0.45) stay usable, which an aspect-ratio test would have thrown
        away along with the diagonals.

        A diagonal segment fails both of those tests by construction, so it gets
        the PCA test instead: thin across its own principal axis and clearly
        longer along it. Callers must then offset with `anchor_normal()`, not
        `anchor()`.
        """
        if self.fill() >= MIN_BBOX_FILL and self.thickness() <= MAX_THICKNESS:
            return True
        return not self.is_axis_aligned() and self.thin_and_long()

    def __repr__(self):
        return "Line(%s, x %d..%d, y %d..%d, %s)" % (
            self.kind, self.x0, self.x1, self.y0, self.y1,
            "horizontal" if self.horizontal else "vertical")


def _classify(r, g, b):
    if g >= MIN_CHANNEL and g - r >= MIN_DOMINANCE and g - b >= MIN_DOMINANCE:
        return "door"
    if b >= MIN_CHANNEL and b - r >= MIN_DOMINANCE and b - g >= MIN_DOMINANCE:
        return "transition"
    return None


def _cluster(points):
    """8-connected components."""
    remaining = set(points)
    out = []
    while remaining:
        seed = remaining.pop()
        comp = [seed]
        stack = [seed]
        while stack:
            cx, cy = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p in remaining:
                        remaining.discard(p)
                        comp.append(p)
                        stack.append(p)
        out.append(comp)
    return out


_cache = {}


def area_lines(area_resref, game=mc.DEFAULT_GAME):
    """All marker segments in one area's map art. Cached."""
    key = area_resref.lower()
    if key in _cache:
        return _cache[key]

    tex = mc.load_map_texture(area_resref, game)
    if tex is None:
        _cache[key] = []
        return []

    px = tex.load()
    w, h = tex.size
    buckets = {"door": [], "transition": []}
    for y in range(h):
        for x in range(w):
            kind = _classify(*px[x, y])
            if kind:
                buckets[kind].append((x, y))

    lines = []
    for kind, pts in buckets.items():
        for comp in _cluster(pts):
            if len(comp) >= MIN_CLUSTER:
                lines.append(Line(kind, comp))
    _cache[key] = lines
    return lines


def nearest_line(area_resref, px, py, max_dist=12.0, kinds=None,
                 game=mc.DEFAULT_GAME):
    """The marker segment nearest a map pixel, or None."""
    best, best_d = None, float("inf")
    for line in area_lines(area_resref, game):
        if kinds and line.kind not in kinds:
            continue
        if not line.usable_as_anchor():
            continue
        d = line.distance(px, py)
        if d < best_d:
            best, best_d = line, d
    if best is None or best_d > max_dist:
        return None
    return best


if __name__ == "__main__":
    import sys
    import os

    if len(sys.argv) < 2:
        print("usage: tools/map_art_lines.py <module_name>")
        raise SystemExit(2)
    mod = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules", sys.argv[1] + ".rim"))
    if mod is None:
        print("no map data for", sys.argv[1])
        raise SystemExit(1)
    cal = mod.calibration
    lines = area_lines(mod.area)
    print("%s: %d marker segments" % (mod.area, len(lines)))
    for line in sorted(lines, key=lambda l: (l.kind, l.x0)):
        print("   %-11s x %3d..%-3d y %3d..%-3d  centre (%5.1f,%5.1f)  len %2d  %s"
              % (line.kind, line.x0, line.x1, line.y0, line.y1, line.cx, line.cy,
                 line.length(), "horizontal" if line.horizontal else "vertical"))
    print("\nnotes and the segment each one is near:")
    for n in mod.notes:
        p = cal.to_pixel(n.x, n.y)
        line = nearest_line(mod.area, p[0], p[1])
        if line is None:
            print("   #%-3d %-22s px%s   (no segment within 12 px)"
                  % (n.index, mc.strref_text(n.strref), p))
        else:
            a = line.anchor(p[0], p[1])
            print("   #%-3d %-22s px%s   %-11s centre (%.1f,%.1f) -> anchor (%.1f,%.1f)"
                  % (n.index, mc.strref_text(n.strref), p, line.kind,
                     line.cx, line.cy, a[0], a[1]))
