"""Propose corrected KOTOR 1 map-note positions automatically.

Phase 2 of AREA-MAP-NOTE-FIX-PLAN.md. The point is that nobody hand-places 340
notes: every proposal here is derived from the game's own data, with a stated
reason, so the human job is approve/override rather than author-from-scratch.

Two ground-truth sources, both exact, both in the game files
-----------------------------------------------------------
1. TRANSITIONS. A note called "To Undercity" / "Exit" / "Path South" names an
   actual door or trigger in the same `.git`, which carries a `TransitionDestin`
   strref (the destination's own name in dialog.tlk) and a `LinkedToModule`.
   Match the note's name against the transition's destination name and snap to
   it. Self-verifying: a note called "To X" sitting away from the only exit
   leading to X *is* the bug, and that exit is the answer.

2. ROOMS. `map_geometry.py` gives every area's rooms as walkable floor polygons
   in world coordinates (from `<area>.lyt` + per-room `.wok`). A note that names
   a room belongs at that room's centre; a note that is off walkable floor
   entirely is unambiguously wrong and gets pulled onto the floor.

3. DOORS. A GREEN segment in the map art is a door, and a door means a room that
   can be entered, so a note marking one belongs INSIDE that room, centred -
   not offset beside the line (user specification, 2026-08-28). Blue segments
   are area transitions: those keep the "just clear of the line" offset, because
   what they lead to is another module, not a room on this map.

Two rules that apply to every proposal, whatever produced it (same specification)
--------------------------------------------------------------------------------
- `_enforce_walkable()`: a proposed position is never left outside the walkable
  area. If it is, it is pulled onto the nearest room's floor and re-snapped to a
  whole map pixel.
- `_flag_reviews()`: a proposal that lands in a DIFFERENT ROOM than BioWare's, or
  moves further than REVIEW_MOVE_PX, is flagged. Flagged proposals are held out
  of the exe table by `note_corrections.py` until a human decides them in
  `output/note_decisions.csv`. Every `door_room` proposal is flagged by
  construction - crossing into the next room is what the rule does.

Deliberate conservatism (fact 3 of the plan: "on walkable floor" is not the
goal, notes must be placed *precisely*):
  - A room centre is only proposed when the room is COMPACT and holds exactly
    ONE note. An open Dantooine plain is one huge room; its centre says nothing
    about where "Strange Ruins" belongs, so no proposal is made there.
  - Moves below MIN_MOVE_PX are not worth an edit (the median note is already
    2.2 px from the nearest object).
  - Everything else is reported as "no proposal", with the reason, rather than
    guessed at.

Commands
--------
  propose [out.csv] [--all]
        Every note in the game: proposal, rule, reason, confidence. Writes a
        CSV that feeds either delivery mechanism unchanged. --all also lists
        the notes left alone.

  render <module> [outdir] [zoom]
  renderall [outdir] [zoom]
        Before/after PNG: room floors outlined, current position in red, the
        proposal in green with an arrow. This is the review surface - approving
        340 proposals by eye is a different job from authoring 340 positions.

  residuals
        Phase 1b: using the transition matches as ground truth, is each module's
        error a single systematic shift, or independent per note?

  show <module>
        Everything known about one module's notes, as text.
"""

from __future__ import annotations

import os
import sys
import csv
import math
import re

import map_calibration as mc
import map_geometry as mg
import map_art_lines as mal

# --- thresholds. All distances in vanilla map pixels unless stated. ---
MIN_MOVE_PX = 3.0        # below this an edit is not worth making
MAX_SNAP_PX = 30.0       # a transition candidate must be this close to the note
MAX_SNAP_PX_OOB = 150.0  # ...unless the note is off-map, where anything is better
NAME_SCORE_MIN = 0.5     # token-overlap floor for accepting a transition match
COMPACT_DIAG_PX = 80.0   # a room bigger than this says nothing about a note
OFF_FLOOR_WORLD = 12.0   # nearest room must be this close to adopt the note
MAX_ROOM_MOVE_PX = 60.0  # a room-centre move beyond this is reported low-confidence
NEAR_TRANSITION_PX = 20.0  # unnamed fallback: a "To X" note this close to an exit
SOLE_TRANSITION_PX = 40.0  # ...relaxed when the module has exactly one exit
OBJECT_SCORE_MIN = 0.75  # object-name matching is stricter than transition matching
OBJECT_SNAP_PX = 20.0
ON_TRANSITION_PX = 6.0   # a note this close to an exit is already marking it
ON_DOOR_PX = 7.0         # ...same for a doorway (shops/apartments are marked by their door)
LINE_SNAP_PX = 16.0      # a transition anchor within this of a drawn marker line snaps to it
LINE_GAP_PX = 4.0        # ...sitting this far clear of the line (icon is 3.5 map px
                         # wide; 3 px left its edge touching the line - open item 1)
LINE_CENTRE_MAX_LEN = 24 # longer than this is a wall strip, not a doorway marker:
DOOR_NEAR_PX = 7.0       # a note this close to a GREEN door line is marking that door
DOOR_PROBE_PX = 12       # how far to probe each side of a door for a room
DOOR_AMBIG_RATIO = 0.6   # two rooms this similar in size: cannot tell which is meant
REVIEW_MOVE_PX = 25.0    # a move this big goes to the human whatever the rule says
GATE_PULL_PX = 8.0       # ...so does a big pull by the walkable-floor gate
WALK_EPS = 0.05          # world units. A room centroid can land exactly ON a
                         # triangle edge, where point-in-triangle fails on float
                         # rounding although the distance to the floor is 0.0.
                         # That point IS walkable, so test with a tolerance.
                         # use it for the perpendicular offset only, not for centring

_STOP = {"to", "the", "a", "an", "into", "towards", "toward", "of"}

# A note whose name is a direction rather than a place. These belong AT the
# transition, which for many is the map edge - so the room rule must never touch
# them (fact 3 of the plan: centring such a note actively makes it wrong).
_TRANSITION_WORDS = {"exit", "entrance", "path", "elevator", "transition",
                     "ramp", "airlock", "stairs", "turbolift", "docking"}

# A note that names a place you stand in, not an object in it. For these the
# room centre beats any object match.
# A note naming a PASSAGE names the way through itself, not a place behind a
# door, so the green-door rule must not send it into an adjoining room. Found by
# looking at the first pass's crops: "North Corridor", "South Corridor" and
# "East Hallway B" were the only three of 18 that went somewhere wrong, and all
# three were pushed out of the passage they name into a side room.
_PASSAGE_WORDS = {"corridor", "hallway", "hall", "passage", "passageway",
                  "walkway", "catwalk", "ramp", "stairs", "stairway", "landing"}

_ROOM_WORDS = {"room", "corridor", "quarters", "hold", "bay", "hangar", "chamber",
               "compound", "barracks", "office", "apartment", "apartments", "cell",
               "deck", "block", "lounge", "kitchen", "dormitory", "bedroom",
               "garage", "cantina", "enclave", "base", "camp", "settlement",
               "village", "estate", "academy", "temple", "tomb", "cave", "ruins",
               "post", "hall", "bunks", "cockpit", "engine", "armory", "dock"}


# --------------------------------------------------------------------------
# name matching
# --------------------------------------------------------------------------
def normalize_name(text):
    """Tokens of a place name, comparable across the two naming conventions.

    Map notes are authored bare ("To Undercity", "Cantina"); TransitionDestin
    strings are authored as "<Planet> - <Place>" ("Taris - Undercity"). Drop the
    planet prefix, the directional filler, and punctuation.
    """
    if not text:
        return set()
    t = text.strip()
    if " - " in t:
        t = t.split(" - ", 1)[1]
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return {w for w in t.split() if w and w not in _STOP}


def name_score(a, b):
    """0..1 overlap between two place names. 1.0 for the same name."""
    ta, tb = normalize_name(a), normalize_name(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    return len(ta & tb) / float(min(len(ta), len(tb)))


def _resref_tokens(resref):
    """Tokens hidden inside an internal resref/tag: sta45b_east_45a -> {east}.
    Numbers and the area-code fragments they are glued to carry no meaning, so
    only alphabetic runs of 3+ characters survive. This is what lets a note
    match an exit whose TransitionDestin names the destination generically
    ('Star Forge - Deck 1') while its tag names the side ('east')."""
    if not resref:
        return set()
    return {w for w in re.findall(r"[a-z]{3,}", resref.lower()) if w not in _STOP}


def transition_score(note_name, tr, game=mc.DEFAULT_GAME):
    """Best of the destination-name match and the tag/template match."""
    by_dest = name_score(note_name, mc.strref_text(tr.dest_strref, game))
    ntok = normalize_name(note_name)
    rtok = _resref_tokens(tr.tag) | _resref_tokens(tr.template)
    by_tag = 0.0
    if ntok and rtok:
        hits = len(ntok & rtok)
        if hits:
            # A tag is not a sentence: one solid word ('east', 'undercity') is
            # a real signal, so score against the note's tokens alone.
            by_tag = hits / float(len(ntok))
    return max(by_dest, by_tag)


def is_transition_name(text):
    if not text:
        return False
    if text.strip().lower().startswith("to "):
        return True
    return bool(normalize_name(text) & _TRANSITION_WORDS)


def is_passage_name(text):
    return bool(_PASSAGE_WORDS & normalize_name(text))


def is_room_name(text):
    return bool(normalize_name(text) & _ROOM_WORDS)


# --------------------------------------------------------------------------
class Proposal:
    __slots__ = ("note", "rule", "reason", "confidence", "new_x", "new_y",
                 "old_px", "new_px", "move_px", "room", "review", "review_reason")

    def __init__(self, note, rule, reason, confidence, new_x, new_y,
                 old_px, new_px, room=None):
        self.note, self.rule, self.reason = note, rule, reason
        self.confidence = confidence
        self.new_x, self.new_y = new_x, new_y
        self.old_px, self.new_px = old_px, new_px
        self.move_px = math.hypot(new_px[0] - old_px[0], new_px[1] - old_px[1])
        self.room = room
        # Set by _flag_reviews()/the rules: this one is not applied automatically,
        # it waits for a human decision in output/note_decisions.csv.
        self.review, self.review_reason = False, ""

    def flag(self, why):
        self.review = True
        self.review_reason = (self.review_reason + "; " + why) if self.review_reason else why

    def move_to(self, cal, x, y):
        self.new_x, self.new_y = x, y
        self.new_px = cal.to_pixel(x, y)
        self.move_px = math.hypot(self.new_px[0] - self.old_px[0],
                                  self.new_px[1] - self.old_px[1])


def _px_dist(cal, ax, ay, bx, by):
    p, q = cal.to_pixel(ax, ay), cal.to_pixel(bx, by)
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _room_diag_px(cal, room):
    lo, hi = cal.to_pixel(room.x0, room.y0), cal.to_pixel(room.x1, room.y1)
    return math.hypot(hi[0] - lo[0], hi[1] - lo[1])


def match_transitions(mod, game=mc.DEFAULT_GAME):
    """Greedy one-to-one note <-> transition matching.

    Returns {note_index: (transition, score, px_distance)}. One-to-one because a
    transition is a single physical place: two notes naming the same destination
    (Taris has two "To Apartments") are two different doors.

    Pass 1 matches by name. Pass 2 catches the notes whose name genuinely cannot
    match - Korriban's "To Dreshdae" leads through a door whose destination
    string is "Sith Academy Entrance" - by taking the one nearby exit on
    geometry alone, but only for notes that are *about* going somewhere, and only
    when the choice is unambiguous.
    """
    cal = mod.calibration
    cands = []
    for note in mod.notes:
        note_name = mc.strref_text(note.strref, game)
        if not note_name:
            continue
        oob = not cal.in_bounds(*cal.to_pixel(note.x, note.y))
        ceiling = MAX_SNAP_PX_OOB if oob else MAX_SNAP_PX
        for tr in mod.transitions:
            score = transition_score(note_name, tr, game)
            if score < NAME_SCORE_MIN:
                continue
            d = _px_dist(cal, note.x, note.y, tr.x, tr.y)
            if d > ceiling:
                continue
            cands.append((-score, d, note.index, tr))

    cands.sort(key=lambda c: (c[0], c[1]))
    taken_notes, taken_trs, out = set(), set(), {}
    for negscore, d, note_index, tr in cands:
        tr_key = (tr.kind, tr.index)
        if note_index in taken_notes or tr_key in taken_trs:
            continue
        taken_notes.add(note_index)
        taken_trs.add(tr_key)
        out[note_index] = (tr, -negscore, d)

    # --- pass 2: geometry only, for "To X" notes with no name match ---
    # Globally greedy: nearest note/exit pair in the whole module wins first.
    # Walking notes in index order instead gets manm28ad wrong - "To Kolto
    # Control" (31 px from the module's only door) would claim it before
    # "To Hrakert Station" (2.2 px from that same door, and obviously its note).
    fallback = []
    for note in mod.notes:
        if note.index in taken_notes:
            continue
        if not is_transition_name(mc.strref_text(note.strref, game)):
            continue
        for tr in mod.transitions:
            fallback.append((_px_dist(cal, note.x, note.y, tr.x, tr.y), note.index, tr))
    fallback.sort(key=lambda c: c[0])

    # A shop interior with one door and a note called "Exit" is not an ambiguous
    # case, so it does not need the tight ceiling.
    ceiling = (SOLE_TRANSITION_PX if len(mod.transitions) == 1
               else NEAR_TRANSITION_PX)
    for d, note_index, tr in fallback:
        tr_key = (tr.kind, tr.index)
        if note_index in taken_notes or tr_key in taken_trs:
            continue
        if d > ceiling:
            continue
        # Ambiguous is worse than unfixed: require a clear winner among the
        # exits still unclaimed at this point.
        others = sorted(dd for dd, ni, tt in fallback
                        if ni == note_index and (tt.kind, tt.index) not in taken_trs
                        and (tt.kind, tt.index) != tr_key)
        if others and others[0] < d * 1.5:
            continue
        taken_notes.add(note_index)
        taken_trs.add(tr_key)
        out[note_index] = (tr, 0.0, d)
    return out


_TEMPLATE_TYPES = {"utp": 2044, "utc": 2027, "utd": 2042, "utt": 2032,
                   "utw": 2058, "uts": 2046, "utm": 2051, "ute": 2029}


class ObjectNames:
    """Display names for a module's gameplay objects.

    An object's `.git` entry only carries a TemplateResRef; the human-readable
    name lives in the template's `LocName` - "Star map", "Ritual Marker",
    "Force Field Control". That makes a third exact anchor: a note that names a
    thing rather than a place can be matched to the thing itself.
    """

    def __init__(self, resources, game=mc.DEFAULT_GAME):
        self.resources = resources
        self.game = game
        self._by_module = {}

    def for_module(self, module_name):
        if module_name in self._by_module:
            return self._by_module[module_name]
        from pykotor.resource.formats.rim import read_rim
        from pykotor.resource.formats.gff import read_gff

        names = {}
        path = os.path.join(self.game, "modules", module_name + "_s.rim")
        if os.path.exists(path):
            try:
                rim = read_rim(path)
            except Exception:
                rim = []
            for res in rim:
                if res.restype.extension not in _TEMPLATE_TYPES:
                    continue
                try:
                    gff = read_gff(res.data)
                except Exception:
                    continue
                names[str(res.resref).lower()] = self._name_of(gff)
        self._by_module[module_name] = names
        return names

    def _name_of(self, gff):
        loc = gff.root.acquire("LocName", None)
        strref = getattr(loc, "stringref", -1) if loc is not None else -1
        if strref is not None and strref >= 0:
            return mc.strref_text(strref, self.game)
        return ""

    def lookup(self, module_name, resref):
        """Display name for one template, falling back to the shared
        templates.bif for generic placeables the module does not carry."""
        if not resref:
            return ""
        key = resref.lower()
        mod_names = self.for_module(module_name)
        if key in mod_names:
            return mod_names[key]
        from pykotor.resource.formats.gff import read_gff
        for restype in _TEMPLATE_TYPES.values():
            data = self.resources.fetch(key, restype)
            if data:
                try:
                    name = self._name_of(read_gff(data))
                except Exception:
                    name = ""
                mod_names[key] = name
                return name
        mod_names[key] = ""
        return ""


def match_objects(mod, note, note_name, obj_names, game=mc.DEFAULT_GAME):
    """Nearest gameplay object whose display name matches the note's, or None.

    Stricter than transition matching: an object match has to be a near-exact
    name, because "Computer" would otherwise attach itself to any console on the
    level. Several identical objects (three Mandalorian Swoops for one "Swoop
    Bikes" note) are not ambiguous - the nearest one is the right anchor.
    """
    cal = mod.calibration
    best = None
    for list_name, tag, template, x, y in mod.objects_full:
        disp = obj_names.lookup(mod.name, template)
        score = max(name_score(note_name, disp),
                    len(normalize_name(note_name) & _resref_tokens(tag))
                    / float(len(normalize_name(note_name)) or 1))
        if score < OBJECT_SCORE_MIN:
            continue
        d = _px_dist(cal, note.x, note.y, x, y)
        if d > OBJECT_SNAP_PX:
            continue
        if best is None or d < best[0]:
            best = (d, score, list_name, disp or tag or template, x, y)
    return best


def _walkable(geom, x, y):
    """Is this world position on walkable floor? Tolerant of the floor's own
    boundary - see WALK_EPS."""
    if geom.on_floor(x, y):
        return True
    _room, d = geom.nearest_room(x, y)
    return d <= WALK_EPS


def door_room(mod, cal, geom, note, room_users):
    """A GREEN line means a room that can be entered, so the note marking that
    door belongs INSIDE the room, at its centre (user specification 2026-08-28).

    Returns (room, line, ambiguous, other_room) or None.

    This supersedes the older "already on a doorway, leave it alone" guard. That
    guard existed because the room rule was dragging tar_m02ac's "Equipment
    Emporium" into the *corridor* the note technically stands in; going through
    the door instead puts it in the shop the note actually names, which is what
    the guard was protecting against in the first place.

    Which of the two rooms a door joins is "the room that can be entered" cannot
    be read from the art, so: probe both sides for walkable floor, and prefer the
    more enclosed room - a shop or cabin is smaller than the corridor outside it.
    When the two are of similar size that reasoning does not hold, so the note is
    flagged for a human instead of guessed at.
    """
    if geom is None:
        return None
    npx = cal.to_pixel(note.x, note.y)
    line = mal.nearest_line(mod.area, npx[0], npx[1], DOOR_NEAR_PX,
                            kinds=("door",))
    if line is None:
        return None

    aligned = line.is_axis_aligned()
    found = {}
    for side in (1.0, -1.0):
        for gap in range(2, DOOR_PROBE_PX + 1):
            if aligned:
                ax, ay = line.anchor(gap=float(gap), side=side)
            else:
                ax, ay = line.anchor_normal(gap=float(gap), side=side)
            room = geom.room_at(*cal.to_world(ax, ay))
            if room is not None:
                found[side] = room
                break

    rooms = {r.name: r for r in found.values()}
    if not rooms:
        return None
    ordered = sorted(rooms.values(), key=lambda r: r.area)
    chosen, other = ordered[0], (ordered[1] if len(ordered) > 1 else None)
    ambiguous = other is not None and chosen.area / other.area > DOOR_AMBIG_RATIO

    # Centring in a big room says nothing (an Ebon Hawk cabin yes, a Dantooine
    # plain no), and a room that already has its own note must not get a second.
    if _room_diag_px(cal, chosen) > COMPACT_DIAG_PX:
        return None
    others = [i for i in room_users.get(chosen.name, []) if i != note.index]
    if others:
        return None
    return chosen, line, ambiguous, other


def _enforce_walkable(results, cal, geom):
    """Correction 2 (user, 2026-08-28): a note must never sit outside the
    walkable area. Individual rules try to respect that; this is the backstop
    that applies to every proposal, whichever rule produced it - the object snap
    in particular never checked, so it could put a marker inside a wall.

    A pulled position is re-snapped to a whole map pixel, because the engine
    draws at int(px + 0.5) and a fractional anchor sits on that boundary.
    """
    if geom is None:
        return
    for p in results:
        if p.rule == "none" or _walkable(geom, p.new_x, p.new_y):
            continue
        near, _d = geom.nearest_room(p.new_x, p.new_y)
        if near is None:
            continue
        fx, fy = near.nearest_floor_point(p.new_x, p.new_y)
        cx, cy = near.centroid_on_floor()
        # Step in from the floor edge until the whole-pixel position is itself on
        # floor; the closest floor point lies exactly ON the boundary, where
        # rounding can push it back off.
        landed = None
        for t in (0.0, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0):
            tx, ty = fx + (cx - fx) * t, fy + (cy - fy) * t
            wx, wy = cal.to_world(*[float(v) for v in cal.to_pixel(tx, ty)])
            if _walkable(geom, wx, wy):
                landed = (wx, wy)
                break
        if landed is None:
            landed = (cx, cy)
        before = p.new_px
        p.move_to(cal, *landed)
        pull = math.hypot(p.new_px[0] - before[0], p.new_px[1] - before[1])
        p.reason += ("; pulled %.0f px onto walkable floor of %s"
                     % (pull, near.name))
        if pull >= GATE_PULL_PX:
            p.flag("the walkable-floor gate moved it %.0f px" % pull)


def _flag_reviews(results, cal, geom, home):
    """Correction 3 (user, 2026-08-28): anything that lands far from where
    BioWare put it - a different room entirely - goes to the human rather than
    straight into the exe table."""
    for p in results:
        if p.rule == "none" or p.move_px < MIN_MOVE_PX:
            continue
        if p.move_px >= REVIEW_MOVE_PX:
            p.flag("moves %.0f px from the vanilla position" % p.move_px)
        if p.rule == "clamp_to_map":
            p.flag("vanilla position is off the map image; no exact answer exists")
        if geom is None:
            continue
        old_room, old_d = home[p.note.index]
        new_room = geom.room_at(p.new_x, p.new_y)
        # Only meaningful when the vanilla note was genuinely inside a room: a
        # note that was off the floor to begin with has no "own room" to leave.
        # door_room is exempt - crossing into the next room is the whole point.
        if (p.rule != "door_room" and old_room is not None and old_d == 0.0
                and new_room is not None and new_room.name != old_room.name):
            p.flag("lands in room %s, vanilla was in %s"
                   % (new_room.name, old_room.name))


def propose_module(mod, resources, game=mc.DEFAULT_GAME, obj_names=None):
    """All proposals for one module, plus a reason for every note left alone."""
    cal = mod.calibration
    geom = mg.load_area_geometry(mod.area, resources)
    matches = match_transitions(mod, game)
    if obj_names is None:
        obj_names = ObjectNames(resources, game)

    # Which room does each note belong to? Needed before any proposal, because
    # "is this room's centre meaningful" depends on how many notes share it.
    home = {}
    for note in mod.notes:
        if geom is None:
            home[note.index] = (None, None)
            continue
        room = geom.room_at(note.x, note.y)
        if room is not None:
            home[note.index] = (room, 0.0)
        else:
            near, d = geom.nearest_room(note.x, note.y)
            home[note.index] = ((near, d) if d <= OFF_FLOOR_WORLD else (None, d))
    room_users = {}
    for idx, (room, _d) in home.items():
        if room is not None:
            room_users.setdefault(room.name, []).append(idx)

    results = []
    for note in mod.notes:
        old_px = cal.to_pixel(note.x, note.y)
        drawn = cal.in_bounds(*old_px)
        room, room_d = home[note.index]
        note_name = mc.strref_text(note.strref, game)
        transition_note = is_transition_name(note_name)

        # --- rule 1: this note names a transition, and we found it ---
        if note.index in matches:
            tr, score, d = matches[note.index]
            ax, ay = tr.x, tr.y
            line_note = ""
            # Refine onto the DRAWN marker line: centred along it, just clear of
            # it on the approach side. A transition object's position is not
            # centred on its own line (m12aa: line centre x 274.5, trigger
            # centroid x 272, and vanilla had the note at 274), and the drawn
            # line is what the player actually looks at.
            seed = cal.to_pixel(tr.x, tr.y)
            line = mal.nearest_line(mod.area, seed[0], seed[1], LINE_SNAP_PX)
            if line is not None:
                # Side: the note's own side of the line, unless the note sits
                # practically ON the line, where its side is meaningless noise -
                # then the transition object decides.
                npx = cal.to_pixel(note.x, note.y)
                diagonal = not line.is_axis_aligned()
                # Only a short segment's midpoint marks the way through; for a
                # long wall strip keep the door object's own along-axis position.
                long_strip = (line.axis_length() if diagonal else line.length()) \
                    > LINE_CENTRE_MAX_LEN
                if diagonal:
                    # Offset along the segment's true normal, centred along its
                    # principal axis (open item 5). An axis-aligned offset from a
                    # diagonal lands in open floor beside the door, not before it.
                    perp = line.perp_offset(*npx)
                    side = line.side_of_normal(*(npx if abs(perp) >= 2.0 else seed))
                    mk = (lambda s: line.anchor_normal(
                        gap=LINE_GAP_PX, side=s,
                        along_seed=seed if long_strip else None))
                else:
                    perp = (npx[1] - line.cy) if line.horizontal else (npx[0] - line.cx)
                    side = line.side_of(*(npx if abs(perp) >= 2.0 else seed))
                    along = None
                    if long_strip:
                        along = seed[0] if line.horizontal else seed[1]
                    mk = (lambda s: line.anchor(gap=LINE_GAP_PX, side=s, along=along))
                lx, ly = mk(side)
                wx, wy = cal.to_world(lx, ly)
                # Sanity: if that side is not walkable but the other is, flip.
                if geom is not None and not _walkable(geom, wx, wy):
                    mx, my = mk(-side)
                    mwx, mwy = cal.to_world(mx, my)
                    if _walkable(geom, mwx, mwy):
                        lx, ly, wx, wy = mx, my, mwx, mwy
                        side = -side
                ax, ay = wx, wy
                line_note = ("; %s its drawn %s%s line (%d px long) and set %.0f px "
                             "clear of it"
                             % ("offset from" if long_strip else "centred on",
                                "diagonal " if diagonal else "", line.kind,
                                line.axis_length() if diagonal else line.length(),
                                LINE_GAP_PX))
            new_px = cal.to_pixel(ax, ay)
            if score <= 0.0:
                reason = ("the only exit nearby is %s %s -> %s (%s), %.0f px away; "
                          "matched on position, not name%s"
                          % (tr.kind, tr.tag or tr.template, tr.linked_module or "?",
                             mc.strref_text(tr.dest_strref, game), d, line_note))
                conf = "medium" if d <= 10.0 else "low"
            else:
                reason = ("names %s %s -> %s (%s), name match %.2f%s"
                          % (tr.kind, tr.tag or tr.template, tr.linked_module or "?",
                             mc.strref_text(tr.dest_strref, game), score, line_note))
                conf = "high" if (score >= 0.9 and d <= 20.0) else "medium"
            results.append(Proposal(note, "transition", reason, conf,
                                    ax, ay, old_px, new_px, room))
            continue

        # --- rule 2: this note names a THING, and that thing is right there ---
        if not is_room_name(note_name):
            hit = match_objects(mod, note, note_name, obj_names, game)
            if hit is not None:
                d, score, list_name, disp, ox, oy = hit
                new_px = cal.to_pixel(ox, oy)
                results.append(Proposal(
                    note, "object",
                    "names the %s %r (%s), %.0f px away, name match %.2f"
                    % (list_name.replace(" List", "").replace("List", "").strip().lower()
                       or "object", disp, list_name, d, score),
                    "high" if score >= 0.99 and d <= 12.0 else "medium",
                    ox, oy, old_px, new_px, room))
                continue

        if geom is None:
            results.append(Proposal(note, "none", "area has no room geometry",
                                    "n/a", note.x, note.y, old_px, old_px, None))
            continue

        off_floor = room_d != 0.0 or room is None
        sole = room is not None and len(room_users[room.name]) == 1
        diag = _room_diag_px(cal, room) if room is not None else None
        compact = diag is not None and diag <= COMPACT_DIAG_PX

        # A "To X" / "Exit" note belongs AT its transition, which is often the
        # map edge. Centring it in a room moves it away from the thing it names,
        # so if rule 1 could not find the transition, leave it alone and say so.
        if transition_note and not (off_floor and room is not None):
            results.append(Proposal(
                note, "none",
                "names a transition but no exit matched it (%d in this module); "
                "centring it in a room would be wrong" % len(mod.transitions),
                "n/a", note.x, note.y, old_px, old_px, room))
            continue

        # A note already sitting ON an exit or a doorway is where it belongs,
        # whatever its name suggests, so the room rule must not touch it.
        #   - exits: manm28aa's "Submersible" is the way off the level but reads
        #     as an object, so the name-based guard above misses it.
        #   - doors: BioWare marks a shop or apartment by its DOOR, and the room
        #     the note technically stands in is then the corridor outside, not
        #     the named place. tar_m02ac's "Equipment Emporium" sits 2 px from
        #     the shop door and the room rule was pulling it 16 px into the
        #     corridor - away from the shop it names.
        on_exit = on_door = float("inf")
        if not off_floor:
            on_exit = min([_px_dist(cal, note.x, note.y, tr.x, tr.y)
                           for tr in mod.transitions] or [float("inf")])
            on_door = min([_px_dist(cal, note.x, note.y, ox, oy)
                           for lst, _t, _tpl, ox, oy in mod.objects_full
                           if lst == "Door List"] or [float("inf")])
            if on_exit <= ON_TRANSITION_PX:
                results.append(Proposal(
                    note, "none",
                    "already on an exit (%.0f px); it marks that way through, so "
                    "leave it there" % on_exit,
                    "n/a", note.x, note.y, old_px, old_px, room))
                continue

        # --- rule 2b: a green door line marks a room that can be entered, so
        #     the note belongs inside that room, centred (user spec) ---
        if not transition_note and not is_passage_name(note_name):
            hit = door_room(mod, cal, geom, note, room_users)
            if hit is not None:
                dr, dline, ambiguous, other = hit
                nx, ny = dr.centroid_on_floor()
                new_px = cal.to_pixel(nx, ny)
                reason = ("marks a drawn green door line (%d px long); centred in "
                          "the room it opens into, %s (%.0f px across%s)"
                          % (dline.axis_length(), dr.name, _room_diag_px(cal, dr),
                             ", vs %s on the other side" % other.name if other else
                             ", the only room either side"))
                p = Proposal(note, "door_room", reason,
                             "medium" if not ambiguous else "low",
                             nx, ny, old_px, new_px, dr)
                # Every one of these deliberately crosses into the next room,
                # which is exactly the class the user asked to see (correction 3),
                # so the whole rule goes to review rather than straight in.
                p.flag("green-door rule: moved into the room through the door")
                if ambiguous:
                    p.flag("the door joins two rooms of similar size (%s %.0f, %s "
                           "%.0f): which one the note names cannot be derived"
                           % (dr.name, dr.area, other.name, other.area))
                results.append(p)
                continue

        if on_door <= ON_DOOR_PX:
            results.append(Proposal(
                note, "none",
                "already on a doorway (%.0f px); it marks that way through, and no "
                "room could be derived from the door, so leave it there" % on_door,
                "n/a", note.x, note.y, old_px, old_px, room))
            continue

        # --- rule 3: the note names a room, and that room is unambiguous ---
        if not transition_note and room is not None and sole and compact:
            nx, ny = room.centroid_on_floor()
            new_px = cal.to_pixel(nx, ny)
            move = math.hypot(new_px[0] - old_px[0], new_px[1] - old_px[1])
            conf = "medium" if move <= 25.0 else "low"
            if off_floor:
                conf = "high" if move <= MAX_ROOM_MOVE_PX else "low"
            results.append(Proposal(
                note, "room_centre",
                "%s room %s (%.0f px across), only note in it"
                % ("off walkable floor, nearest is" if off_floor else "sole note in",
                   room.name, diag),
                conf, nx, ny, old_px, new_px, room))
            continue

        # --- rule 4: off the floor, but the room's centre is not usable ---
        if off_floor and room is not None:
            nx, ny = room.nearest_floor_point(note.x, note.y)
            new_px = cal.to_pixel(nx, ny)
            results.append(Proposal(
                note, "clamp_to_floor",
                "off walkable floor; pulled onto nearest floor of %s (%s)"
                % (room.name,
                   "room too large to centre in" if not compact
                   else "%d notes share the room" % len(room_users[room.name])),
                "medium", nx, ny, old_px, new_px, room))
            continue

        # --- rule 5: correctly placed, but outside the map image entirely ---
        # tat_m18ac's "Star Map" is 1 px from the actual Star Map placeable, and
        # 12 of that area's 155 objects also project outside the art: the world
        # position is right and the map image simply does not reach it. Nothing
        # can put the marker on the object, so bring it to the nearest point that
        # is BOTH in bounds and on walkable floor.
        #
        # Walkable, not just in-bounds: the Phase 1a test moved danm16's "Holding
        # Cell" to an in-bounds pixel 24 world units from the nearest room, and
        # the marker could not be seen in game - a corner the player never walks
        # into is not a useful place for a note, whatever the bound check says.
        if not drawn:
            px = min(max(old_px[0], 2), int(mc.MAP_W) - 2)
            py = min(max(old_px[1], 2), int(mc.MAP_H) - 2)
            nx, ny = cal.to_world(px, py)
            detail = "clamped to the nearest map edge"
            if geom is not None:
                near, _d = geom.nearest_room(nx, ny)
                if near is not None:
                    fx, fy = near.nearest_floor_point(nx, ny)
                    fpx = cal.to_pixel(fx, fy)
                    if cal.in_bounds(*fpx):
                        nx, ny, px, py = fx, fy, fpx[0], fpx[1]
                        detail = ("pulled to the nearest walkable floor inside the "
                                  "map, in room %s" % near.name)
            results.append(Proposal(
                note, "clamp_to_map",
                "world position is outside this area's map image, so the engine "
                "never draws it; " + detail,
                "low", nx, ny, old_px, (px, py), room))
            continue

        # --- nothing defensible: say why, do not guess ---
        if room is None:
            why = ("off walkable floor and no room within %.0f world units (nearest %.1f)"
                   % (OFF_FLOOR_WORLD, room_d if room_d is not None else float("nan")))
        elif not sole:
            why = ("on floor of %s, but %d notes share that room"
                   % (room.name, len(room_users[room.name])))
        else:
            why = "on floor of %s, too large to centre in (%.0f px across)" % (room.name, diag)
        results.append(Proposal(note, "none", why, "n/a", note.x, note.y,
                                old_px, old_px, room))

    _enforce_walkable(results, cal, geom)
    _flag_reviews(results, cal, geom, home)
    return results, geom


# --------------------------------------------------------------------------
def _iter_proposals(game=mc.DEFAULT_GAME):
    resources = mg.GameResources(game)
    obj_names = ObjectNames(resources, game)
    for mod in mc.iter_modules(game):
        if not mod.notes:
            continue
        props, geom = propose_module(mod, resources, game, obj_names)
        yield mod, props, geom


def cmd_propose(argv):
    out_csv = None
    show_all = False
    for a in argv:
        if a == "--all":
            show_all = True
        else:
            out_csv = a

    rows = []
    counts = {}
    off_floor_after = []
    for mod, props, geom in _iter_proposals():
        cal = mod.calibration
        for p in props:
            n = p.note
            actionable = p.rule != "none" and p.move_px >= MIN_MOVE_PX
            # correction 2: nothing we place may end up off the walkable area
            if actionable and geom is not None and not _walkable(geom, p.new_x, p.new_y):
                off_floor_after.append((mod.name, n.index, p.rule))
            rule = p.rule if actionable else ("none" if p.rule == "none" else "below_threshold")
            counts[rule] = counts.get(rule, 0) + 1
            rt = cal.to_pixel(p.new_x, p.new_y)
            rows.append({
                "module": mod.name, "area": mod.area,
                "note_index": n.index, "tag": n.tag, "strref": n.strref,
                "name": mc.strref_text(n.strref),
                "rule": rule, "confidence": p.confidence if actionable else "n/a",
                "old_world_x": "%.6f" % n.x, "old_world_y": "%.6f" % n.y,
                "new_world_x": "%.6f" % p.new_x if actionable else "",
                "new_world_y": "%.6f" % p.new_y if actionable else "",
                "old_px": p.old_px[0], "old_py": p.old_px[1],
                "new_px": p.new_px[0] if actionable else "",
                "new_py": p.new_px[1] if actionable else "",
                "move_px": "%.1f" % p.move_px,
                "drawn_before": cal.in_bounds(*p.old_px),
                "drawn_after": cal.in_bounds(*p.new_px),
                "roundtrip_ok": (rt == p.new_px) if actionable else "",
                "room": p.room.name if p.room else "",
                "review": (p.review if actionable else ""),
                "review_reason": (p.review_reason if actionable else ""),
                "reason": p.reason,
            })

    total = len(rows)
    act = [r for r in rows if r["rule"] not in ("none", "below_threshold")]
    print("map notes: %d" % total)
    print("proposals: %d (%.0f%%)   left alone: %d"
          % (len(act), 100.0 * len(act) / total, total - len(act)))
    print("\nby rule:")
    for k in sorted(counts, key=lambda k: -counts[k]):
        print("   %-16s %4d" % (k, counts[k]))
    print("\nby confidence (proposals only):")
    conf = {}
    for r in act:
        conf[r["confidence"]] = conf.get(r["confidence"], 0) + 1
    for k in ("high", "medium", "low"):
        if k in conf:
            print("   %-16s %4d" % (k, conf[k]))

    print("\nproposals still off walkable floor: %d" % len(off_floor_after))
    for m, i, rule in off_floor_after[:10]:
        print("   %s #%d (%s)" % (m, i, rule))

    flagged = [r for r in act if r["review"] is True]
    print("\nheld for manual review: %d of %d proposals" % (len(flagged), len(act)))
    why = {}
    for r in flagged:
        for part in r["review_reason"].split("; "):
            key = re.sub(r"\d+(\.\d+)?", "N", part)
            why[key] = why.get(key, 0) + 1
    for k in sorted(why, key=lambda k: -why[k]):
        print("   %4d  %s" % (why[k], k))

    bad_rt = [r for r in act if r["roundtrip_ok"] is False]
    print("\nround-trip failures (new world -> different pixel): %d" % len(bad_rt))
    for r in bad_rt[:10]:
        print("   %s #%s %s" % (r["module"], r["note_index"], r["name"]))

    fixed = [r for r in act if not r["drawn_before"] and r["drawn_after"]]
    print("notes that never drew and now would: %d" % len(fixed))
    for r in fixed:
        print("   %-14s %-24s px(%s,%s) -> (%s,%s)  [%s]"
              % (r["module"], r["name"], r["old_px"], r["old_py"],
                 r["new_px"], r["new_py"], r["rule"]))
    broke = [r for r in act if r["drawn_before"] and not r["drawn_after"]]
    if broke:
        print("\n!! proposals that would push a drawn note OFF the map: %d" % len(broke))
        for r in broke:
            print("   %-14s %-24s -> px(%s,%s)" % (r["module"], r["name"], r["new_px"], r["new_py"]))

    print("\nbiggest 25 proposed moves:")
    for r in sorted(act, key=lambda r: -float(r["move_px"]))[:25]:
        print("   %-14s %-26s %-14s %5s px  %-6s %s"
              % (r["module"], r["name"][:26], r["tag"][:14], r["move_px"],
                 r["confidence"], r["rule"]))

    if show_all:
        print("\nnotes left alone, by reason:")
        why = {}
        for r in rows:
            if r["rule"] in ("none", "below_threshold"):
                key = re.sub(r"\d+(\.\d+)?", "N", r["reason"])
                why.setdefault(key, []).append(r)
        for k in sorted(why, key=lambda k: -len(why[k])):
            print("   %4d  %s" % (len(why[k]), k))

    if out_csv:
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nwrote %s (%d rows)" % (out_csv, len(rows)))


# --------------------------------------------------------------------------
def cmd_residuals(argv):
    """Phase 1b: is a module's note error one systematic shift, or per-note?"""
    print("Using transition-matched notes as ground truth. If a module's error")
    print("were a single shift, subtracting the mean delta would collapse the")
    print("spread; 'after' >= 'before' means the notes are independently wrong.\n")
    print("%-14s %5s  %-18s %-18s %s"
          % ("module", "n", "mean delta px", "rms before -> after", "verdict"))
    tot_before = tot_after = 0.0
    tot_n = 0
    for mod, props, _geom in _iter_proposals():
        deltas = [(p.new_px[0] - p.old_px[0], p.new_px[1] - p.old_px[1])
                  for p in props if p.rule == "transition"]
        if len(deltas) < 3:
            continue
        n = len(deltas)
        mx = sum(d[0] for d in deltas) / n
        my = sum(d[1] for d in deltas) / n
        rms_b = math.sqrt(sum(d[0] ** 2 + d[1] ** 2 for d in deltas) / n)
        rms_a = math.sqrt(sum((d[0] - mx) ** 2 + (d[1] - my) ** 2 for d in deltas) / n)
        tot_before += rms_b ** 2 * n
        tot_after += rms_a ** 2 * n
        tot_n += n
        verdict = ("systematic shift" if rms_a < 0.5 * rms_b else
                   "partly systematic" if rms_a < 0.8 * rms_b else "per-note")
        print("%-14s %5d  (%+5.1f,%+5.1f)      %5.1f -> %5.1f       %s"
              % (mod.name, n, mx, my, rms_b, rms_a, verdict))
    if tot_n:
        print("\nall modules pooled: rms %.1f -> %.1f px over %d matched notes"
              % (math.sqrt(tot_before / tot_n), math.sqrt(tot_after / tot_n), tot_n))


# --------------------------------------------------------------------------
def cmd_show(argv):
    if not argv:
        print("usage: show <module>")
        return 2
    name = argv[0]
    mod = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules", name + ".rim"))
    if mod is None:
        print("no map data for", name)
        return 1
    resources = mg.GameResources(mc.DEFAULT_GAME)
    props, geom = propose_module(mod, resources)
    cal = mod.calibration
    print("%s (area %s, NorthAxis %d) - %d notes, %d transitions, %d rooms"
          % (mod.name, mod.area, cal.north_axis, len(mod.notes),
             len(mod.transitions), len(geom.rooms) if geom else 0))
    for p in props:
        n = p.note
        print("\n  #%-3d %-18s %s" % (n.index, n.tag, mc.strref_text(n.strref)))
        print("       now  px(%3d,%3d) world (%.3f, %.3f)%s"
              % (p.old_px[0], p.old_px[1], n.x, n.y,
                 "" if cal.in_bounds(*p.old_px) else "   <== NEVER DRAWN"))
        if p.rule == "none":
            print("       no proposal: %s" % p.reason)
        else:
            print("       ->   px(%3d,%3d) world (%.3f, %.3f)  move %.1f px"
                  % (p.new_px[0], p.new_px[1], p.new_x, p.new_y, p.move_px))
            print("       %-6s %-14s %s" % (p.confidence, p.rule, p.reason))


# --------------------------------------------------------------------------
def _font(size):
    from PIL import ImageFont
    for nm in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nm, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_module(mod, props, geom, outdir, zoom=4):
    """Before/after review surface for one module."""
    from PIL import Image, ImageDraw

    cal = mod.calibration
    W, H = int(mc.MAP_W), int(mc.MAP_H)
    tex = mc.load_map_texture(mod.area)
    base = Image.new("RGB", (W, H), (0, 0, 0))
    if tex is not None:
        base.paste(tex, (0, 0))
    img = base.resize((W * zoom, H * zoom), Image.NEAREST)
    canvas = Image.new("RGB", (img.width, img.height + 15 * zoom), (18, 18, 22))
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    small, big = _font(max(10, 3 * zoom)), _font(max(12, 4 * zoom))

    def P(wx, wy):
        px, py = cal.to_pixel(wx, wy, integer=False)
        return (px + 0.5) * zoom, (py + 0.5) * zoom

    # room floors, so it is obvious what "the room" means for each proposal
    if geom is not None:
        for room in geom.rooms:
            for t in room.tris:
                d.polygon([P(*t[0]), P(*t[1]), P(*t[2])], outline=(0, 70, 90))

    for tr in mod.transitions:
        x, y = P(tr.x, tr.y)
        d.rectangle([x - 3, y - 3, x + 3, y + 3], outline=(120, 120, 255))

    for p in props:
        ox, oy = P(p.note.x, p.note.y)
        r = 4 * zoom / 2
        oob = not cal.in_bounds(*p.old_px)
        old_col = (255, 200, 0) if oob else (255, 40, 40)
        d.line([ox - r * 2, oy, ox + r * 2, oy], fill=old_col)
        d.line([ox, oy - r * 2, ox, oy + r * 2], fill=old_col)
        d.ellipse([ox - r, oy - r, ox + r, oy + r], outline=old_col, width=max(1, zoom // 3))

        label = "%d %s" % (p.note.index, mc.strref_text(p.note.strref) or p.note.tag)
        if p.rule == "none" or p.move_px < MIN_MOVE_PX:
            d.text((ox + r * 2 + 2, oy - 6 * zoom / 2), label + "  (unchanged)",
                   fill=(160, 160, 160), font=small)
            continue

        nx, ny = P(p.new_x, p.new_y)
        # the game's real 14x14 icon at the proposed spot
        d.ellipse([nx - 7 * zoom / 2, ny - 7 * zoom / 2,
                   nx + 7 * zoom / 2, ny + 7 * zoom / 2], outline=(255, 255, 255))
        d.line([ox, oy, nx, ny], fill=(0, 255, 120), width=max(1, zoom // 3))
        d.ellipse([nx - r, ny - r, nx + r, ny + r], outline=(0, 255, 120),
                  width=max(2, zoom // 2))
        d.text((nx + r * 2 + 2, ny - 6 * zoom / 2),
               "%s  %s %s +%.0fpx" % (label, p.rule, p.confidence, p.move_px),
               fill=(140, 255, 180), font=small)

    y0 = img.height + 3
    d.text((6, y0), "%s  (area %s, NorthAxis %d)   red=current  green=proposed"
                    "  blue square=transition  teal=walkable floor"
           % (mod.name, mod.area, cal.north_axis), fill=(220, 220, 220), font=big)
    d.text((6, y0 + 5 * zoom),
           "white ring = the game's real 14px icon at the proposed spot",
           fill=(150, 150, 150), font=small)

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "%s.png" % mod.name)
    canvas.save(path)
    return path


def cmd_render(argv):
    if not argv:
        print("usage: render <module> [outdir] [zoom]")
        return 2
    name = argv[0]
    outdir = argv[1] if len(argv) > 1 else os.path.join("output", "mapnotes-proposed")
    zoom = int(argv[2]) if len(argv) > 2 else 4
    mod = mc.load_module(os.path.join(mc.DEFAULT_GAME, "modules", name + ".rim"))
    if mod is None:
        print("no map data for", name)
        return 1
    resources = mg.GameResources(mc.DEFAULT_GAME)
    props, geom = propose_module(mod, resources)
    print("wrote", render_module(mod, props, geom, outdir, zoom))


def cmd_renderall(argv):
    outdir = argv[0] if argv else os.path.join("output", "mapnotes-proposed")
    zoom = int(argv[1]) if len(argv) > 1 else 4
    n = 0
    for mod, props, geom in _iter_proposals():
        render_module(mod, props, geom, outdir, zoom)
        n += 1
    print("rendered %d modules into %s" % (n, outdir))


COMMANDS = {
    "propose": cmd_propose,
    "residuals": cmd_residuals,
    "show": cmd_show,
    "render": cmd_render,
    "renderall": cmd_renderall,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
