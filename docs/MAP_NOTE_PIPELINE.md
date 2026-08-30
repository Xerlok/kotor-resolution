# MAP-NOTE PIPELINE — how 340 notes became 250 corrections

The RE side of map notes is closed. This is a **content-authoring** pipeline: a
proposal pass derives corrections from the game's own data, a human reviews them,
and a hand-annotation round fixes what rules cannot.

```
.git waypoints (HasMapNote=1)
   -> map_note_survey.py      : where is every note now?
   -> map_note_propose.py     : where should it be, and why?   -> map_note_proposals.csv
   -> map_note_review.py      : which need human eyes?          -> review sheets
   -> map_note_atlas.py       : hand annotation round-trip      -> note_decisions.csv
   -> note_corrections.py     : decisions + proposals, validated -> note_corrections.csv
   -> note_table_patch.py     : build + inject the exe table
```

## The three ground-truth facts that shape everything

From the user's in-game testing, treated as axioms:

1. **Almost every map note is misplaced**, some slightly, some badly. Out of
   bounds is never acceptable.
2. **Player and party markers are correct everywhere.** This is what makes the
   problem tractable: both go through the *same* transform with the *same*
   calibration, so if players are right and notes are wrong, the fault is in the
   notes' authored `XPosition`/`YPosition` and nowhere else.
3. **"On walkable floor" is not the goal.** Notes must be placed *precisely*:
   some belong in the centre of the room they name, some at the map edge where a
   transition is.

Fact 3 kills auto-snapping. Facts 1+3 kill "just scale the icons and
re-evaluate" as a *fix* — a bigger icon on a misplaced note is still misplaced.

## Measured scope

- **340 map notes across 90 modules.** 88 distinct textures (only two pairs share
  art: `ebo_m12aa`+`ebo_m41aa`, and `tat_m17ae`+`tat_m17ag`).
- Max **14** notes in one module (`unk_m44aa`); median 3.
- **339 render; 1 never draws** — `tat_m18ac` "Star Map" at map px (431, −31),
  rejected by the engine's own bound check.
- 2 sit on essentially unmapped black art (`tat_m17aa` "To the Dune Sea",
  `tar_m03aa` "To Undercity"); 10 more are partly over black.
- Distance from a note to the nearest gameplay object, in vanilla px:
  **p50 2.2 · p75 5.1 · p90 9.2 (8.5 after the door fix) · p95 12.5 · p99 22.0 ·
  max 72.5.** Against a fixed 14 px icon, anything past ~7 px already reads as
  "not on the thing it names".
- Worst offenders: `ebo_m41aa` portquarters (72.5), Starboard (53.3), SwoopRacer
  (50.5); `unk_m44aa` Armory (24.0); `tar_m10ac` Loading Bay (22.0);
  `ebo_m12aa` Swoop (21.2), Engine (15.0).

**Distance-to-nearest-object is only a proxy** — it flags notes far from
anything, but a note can be 2 px from an object and still be in the wrong room.
Use it for prioritising, never for auto-correcting.

### Phase 1b, answered: the error is per-note, not per-module

If every note in a module needed the same delta, the fix would collapse from ~340
per-note corrections to ~90 per-module ones. Tested using the 120
transition-matched notes as ground truth: subtracting each module's mean delta
**barely reduces the spread — pooled rms 6.1 → 5.4 px over 71 notes in modules
with ≥3 matches.** Two modules read "systematic" at n=3, which is noise.
**There is no shortcut.** CONFIRMED.

### `tat_m18ac` "Star Map" is NOT misplaced

It sits **1 px from the actual Star Map placeable** (`k_tat_star_map`, LocName
"Star map"). 12 of that area's 155 gameplay objects also project outside the map
art, and object py spans −38..322 against a 0..256 map. **The area's map image
simply does not cover that part of the world** — no authored position can put the
marker on the object. The user chose **vanilla invisibility over an inaccurate
edge marker**, so `clamp_to_map` produces no corrections and the game keeps
exactly one note that never draws, by choice. The rule stays in the code for the
record; it currently fires on nothing.

## Ground-truth sources found in the game data

1. **Transitions.** Doors and triggers in a `.git` carry `TransitionDestin` (a
   **strref** — the destination's own dialog.tlk name) alongside
   `LinkedToModule`/`LinkedTo`. A note called "To Undercity" can be matched to
   the actual Undercity door by name. **Trigger anchors use the centroid of the
   trigger's `Geometry` polygon** (its points are local to the trigger position),
   not the trigger origin.
2. **Room geometry.** `<areaResRef>.lyt` in `data/layouts.bif` lists an area's
   rooms; each room's walkmesh is `<roomModel>.wok` in `data/models.bif`.
3. **Object display names.** A `.git` entry only has a TemplateResRef; the
   human-readable name is `LocName` in the template (`.utp`/`.utc`/… in the
   module's `_s.rim`, else `data/templates.bif`).
4. **The drawn map art itself** — green segments are doors, blue are
   area-transitions (`tools/map_art_lines.py`).

## The rule ladder (priority order, deliberately conservative)

1. **`transition`** — note name matches a door/trigger destination, or its tag
   (`sta45b_east_45a` is how "To East Exit" matches when the destination string
   is the generic "Star Forge - Deck 1"). Greedy one-to-one, **globally greedy by
   distance**. Fallback pass: a "To X"/"Exit" note with no name match takes the
   single nearby exit on geometry alone (≤20 px, or ≤40 px when the module has
   exactly one exit) but only with a clear winner. This is what fixes Korriban's
   "To Dreshdae" (12 px; its door is named "Sith Academy Entrance").
2. **`object`** — the note names a thing whose LocName matches (≥0.75, ≤20 px)
   and the note is not a room name.
3. **`door_room`** — a **green** segment within `DOOR_NEAR_PX` (7) is probed on
   both sides for walkable floor; **the more enclosed of the two rooms wins** (a
   shop/cabin is smaller than the corridor outside it), and the note goes to that
   room's `centroid_on_floor()`. Blue segments keep the "just clear of the line"
   offset — what they lead to is another module, not a room on this map.
4. **`room_centre`** — only when the note's room is compact (≤80 px across) and
   holds exactly **one** note. An open Dantooine plain is one huge room; its
   centre says nothing about where "Strange Ruins" belongs, so nothing is
   proposed there.
5. **`clamp_to_floor`** — off walkable floor, room centre not usable.
6. **`clamp_to_map`** — correctly placed but outside the map image (fires on
   nothing today, by user decision).

**Hard guard: a transition-named note is NEVER room-centred.** Without it the
pass moved Star Forge's "To East/West Exit" 19 px *away* from their doors and
Korriban's "To Dreshdae" 16 px the wrong way.

**Guards and constants:**

| name | value | purpose |
|---|---|---|
| `MIN_MOVE_PX` | 3 | below this a move isn't worth a table entry |
| `LINE_GAP_PX` | **4** (was 3) | clearance from a line's edge; the icon is ~3.5 map px wide, so 3 left its edge touching |
| `LINE_CENTRE_MAX_LEN` | 24 | above this, a strip supplies only the *perpendicular* offset |
| `DOOR_NEAR_PX` | 7 | deliberately tight; only reaches a note already on its door |
| `ON_TRANSITION_PX` | — | a note already on an exit is not recentred |
| `ON_DOOR_PX` | 7 | superseded by `door_room`, kept as fallback |
| `REVIEW_MOVE_PX` | 25 | above this, a human decides |

`_enforce_walkable()` runs over **every** proposal whatever rule produced it (the
object rule never checked, so it could put a marker inside a wall): off-floor
positions are pulled to the nearest room's floor, stepped inward until the
whole-pixel position is itself walkable, and re-snapped to a whole map pixel.
Reported "proposals still off walkable floor" is now **0**, asserted.

`_PASSAGE_WORDS` / `is_passage_name()` excludes passage-named notes from
`door_room` — **a note naming a PASSAGE names the way through itself, not a place
behind a door**. Found by looking at crops: `manm28aa` "East Hallway B",
`unk_m44aa` "North/South Corridor" were being pushed out of the passage they name.

## The line-centring rule

**Root cause, measured.** A transition *object's* position is not centred on its
own drawn line. In `m12aa` the blue segment is x 268..281, y 96..97 — **centre
x 274.5** — while the `AreaTransition` trigger's geometry centroid projects to
x **272**. Vanilla had the note at x **274**: BioWare centred it on the line, and
the object-based snap moved it 2.5 px off. **The drawn line is what the player
looks at, so it is the better anchor.**

`tools/map_art_lines.py` reads door/transition segments straight out of the map
artwork (green = door, blue = transition; a **relative channel-dominance test**,
so it works across the different area palettes).

Three things this needed to get right, each found by looking then measuring:

1. **Fractional anchors broke the round-trip.** A line centre of 274.5, or
   edge+3 = 68.5, sits exactly on the engine's `int(px + 0.5)` boundary, so
   float32 noise decided the pixel — **41 of 171 corrections failed round-trip
   validation.** Anchors are now snapped to whole map pixels inside
   `Line.anchor()`.
2. **A long strip's midpoint is meaningless.** Some maps draw a blue strip down a
   whole wall (`kas_m23ac`: 45 px long, 8 thick) with the actual door at one END.
   Centring on it moved notes 17–25 px the wrong way. A line now supplies the
   **perpendicular** offset always, but the **along-axis** position only when it
   is short (`LINE_CENTRE_MAX_LEN`); otherwise the along-axis comes from the door
   object.
3. **Diagonal streaks are not axis-aligned lines.** `tar_m02af`'s marker runs
   diagonally: a 33×31 bbox at **0.12 fill**. Originally rejected via a
   **bbox fill ≥ 0.25** test (genuine axis-aligned markers measure 0.27–1.00:
   m12aa 14×2 at 1.00, m23ac 8×45 at 0.33, m40ab doors 18×4 at 0.82), chosen over
   an aspect-ratio test which would also have discarded the small compact
   path-end markers (7×7 at 0.45) that were producing good results.
   **Superseded** by the PCA rule below.

**True-normal offset via PCA** (`Line._geom()` / `anchor_normal()` /
`usable_as_anchor()`): take the segment's principal axis from PCA over its
pixels, offset along the real unit **normal**, centre along the real axis. This
unifies axis-aligned and diagonal handling and retired the fill filter.
Verified on `tar_m02af`: the 33×31 blob at 0.12 bbox fill reads as a **43.5 px
segment at 43°, 0.84 px thick**.

Effect: 9 corrections disappeared, and that is the point — with the true
orientation those notes land within ~2 px of BioWare's own position, i.e. vanilla
was right and the old object-snap had been moving them 3–13 px wrongly.

## Review, and the bugs looking found

**Method that worked: triage first, then eyes only where judgement is needed.**
`map_note_review.py` classifies every proposal as self-evident or needing review
and renders zoomed before/after crops tiled into contact sheets. 118 of 187 were
self-evident short snaps onto exactly-name-matched anchors; 69 needed looking at.
**The crops are far more useful than whole-map renders** — at that zoom "does the
14 px icon cover the thing it names" is directly answerable.

Three real bugs found **by looking at the pictures**:

1. **Crossed pairing in the positional fallback.** `manm28ad` has one door;
   "To Kolto Control" (31 px away) claimed it before "To Hrakert Station"
   (2.2 px away, obviously its note) because pass 2 walked notes in index order.
   Fixed: globally greedy by distance.
2. **Notes already on an exit were being recentred** (`end_m01aa` "Escape Pod
   Access", 6 px from its exit). Guarded by `ON_TRANSITION_PX`.
3. **Notes on a shop doorway were pulled into the corridor.** `tar_m02ac`
   "Equipment Emporium" sits 2 px from the shop door; the room it *technically*
   occupies is the corridor outside, so the room rule moved it 16 px AWAY from
   the shop it names. Guarded by `ON_DOOR_PX`; caught 4 notes.

Proposals went 193 → 187; all six removals would have made things worse.

**A heuristic considered and REJECTED:** "a note within 3 px of a waypoint was
placed there deliberately, so never move it." Measured: 11 of 54 `room_centre`
proposals match, but **half the waypoints are incidental NPC patrol/spawn
points** (`WP_korr_citizenmwlk_01`, `tar10_wppool1`, `tar08_wpgas2_2`) rather
than meaningful markers. Does not discriminate; not added. The meaningful ones
(`kas22ab_kas24aa`, `kas24_joleehome`, `k35_way_pcroom1`) were handled as
explicit review decisions instead.

**Verified sound without user input:** all 39 positional exit matches, by
invariant rather than sampling (each matched to its nearest exit AND no other
note closer to that exit — 0 suspect pairings). The 14 "low confidence" matches
were inspected and the label was over-cautious; they are among the clearest fixes
in the set.

## The user's three method corrections (2026-08-28)

1. **"A green line means a room that can be entered, so the note for that room
   goes inside it, centred."** → rule `door_room`. This deliberately supersedes
   the old `ON_DOOR` "leave it alone" guard: that guard existed because the room
   rule dragged "Equipment Emporium" into the corridor; going *through the door*
   puts it in the shop, which is what the guard was protecting in the first place.
2. **"A note must never be outside the walkable area."** → `_enforce_walkable()`.
3. **"If a note lands far from vanilla (another room entirely), give it to me."**
   → `Proposal.review` + `_flag_reviews()`. Triggers: a different walkmesh room
   than vanilla (only when the vanilla note was genuinely on floor), a move
   ≥ 25 px, a ≥ 8 px pull by the walkable gate, an ambiguous door,
   `clamp_to_map`, and **every `door_room` proposal**.

Flagged rows are held **out of the exe table** until `note_decisions.csv` says
approve or override; `finalize` prints them as "awaiting review".

### The one contradiction with an earlier human decision

Five rows were rejected with "named place marked by its doorway — the game's own
convention", which is exactly what correction 1 overrides. Only **two** are
genuine contradictions (`tar_m02ad` #26 Yun's Apartment, `tar_m03ad` #27 Matrik's
Apartment — both now `door_room`, both visually confirmed, both flipped to
approve). The other three (`manm26ae` #70 Tyvark's Shop, #73 Republic Enclave,
`korr_m33aa` #41 Cantina) are **not** contradictions: no room behind their door
exists on that map (the shop/enclave is a separate module), so `door_room`
correctly proposes nothing. Those rejections stand.

## The annotation atlas — the hand-authoring round trip

When rules ran out, the user authored the rest by hand. `tools/map_note_atlas.py`
`build` produces 90 PNGs (one per module with notes, all 340 notes) plus
`atlas_index.csv` (340 rows × 31 columns — the machine-readable half) and a
`README.md` carrying the protocol.

### Design facts (don't re-derive)

- Drawn at **4× the game's map-pixel space** (440×256), so one map pixel is a 4×4
  block and a steady hand is ~±0.75 map px — finer than the engine's own
  rounding. Only the left 440 px are shown.
- A right-hand legend of up to 14 rows always fits at zoom 4 (max notes = 14).
- **Ink colour: MAGENTA `#FF00FF`.** Scanned all 88 distinct map textures:
  **0 magenta pixels**, versus 152 saturated-red pixels (144 of them in `m17ab`).
  Red is a documented fallback; magenta cannot collide with the art. Nothing the
  atlas itself draws is near magenta (markers yellow/green, floor wash teal,
  fiducials cyan).
- **Marker crowding is the only real ambiguity risk and it is small:** 14 of 340
  notes have another note's marker within 12 map px, worst case **1 map px apart**
  (`manm28aa` "Envirosuit Storage" vs "Environment Suit Container", and "Security
  Computer" vs "Security Control"). Those are flagged `crowded`, their badge is
  pushed out to 58 px instead of 30, and the legend tells the reviewer to start
  the line at the badge. Badges are always ≥34 px apart by construction.
- Four **cyan fiducial squares** per page, centres recorded, so a resized or
  cropped return can still be registered.
- Per note: yellow crosshair at the authored position (the identity anchor,
  because the exe table keys on the vanilla world position), a white ring at the
  real 14×14 px icon size, a numbered badge, and — for notes the table already
  moves — a **green cross** where the game draws it today. So the atlas doubles
  as a review surface for corrections already applied.

### The annotation contract

**Draw a magenta line from the note's marker to where the note should be, ending
in a small circle/blob. The end nearest a known marker identifies the note; the
far end is the target.** Identity is geometric — no handwriting recognition.

**Plus the user's own convention, discovered in use:** *"for a few notes I drew
just a blob without a line, it is usually drawn over vanilla yellow note and it
means it was a correct placement."* That is **not** a no-op — where the table was
already auto-moving that note, the move must be **taken back**, written as
`decision=reject`.

### Ingest constants (`map_note_atlas.py`)

| name | value | why |
|---|---|---|
| `SEED_STRENGTH` | 100 | a blob only counts as ink if it contains a properly saturated magenta pixel |
| weak/grow test | `min(R,B) − G > 30 and min(R,B) > 55` | grows the stroke from its seeds so anti-aliased edges aren't clipped |
| `MERGE_GAP_PX` | 14 | hand strokes break into pieces (brush lifts; the end blob drawn as a separate dab) |
| `MIN_INK` | 6 | smaller is a stray pixel |
| `MIN_STROKE_PX` | 3 | under one map px; the reviewer corrects many notes by 1–2 map px |
| `CONFIRM_TIP_PX` | 4.0 | one map px — the confirm/move split |
| `TIP_FRACTION` | 0.75 | pixels this far along the stroke count as "the tip" |
| `ANCHOR_MAX_PX` | 60 | a stroke starting further than this from any marker is unreadable |

**The confirm/move split is measured, not guessed.** Over the reviewer's whole
pass: real short strokes reach **4.8–9.7 px** from the marker; dabs reach
**1.7–3.8 px**. Unambiguous gap. A dab's 1-px "target" is only the rounding of an
off-centre blob.

### Two detection bugs, both real, both fixed

1. **Relation-only ink test produced phantom strokes.** `_is_ink` was a pure
   channel relation and its docstring claimed the map art cannot satisfy it.
   **It can** — dull mauve art passes: `(148,113,148)` on Dantooine,
   `(173,117,165)` on Taris. The first ingest invented **28 phantom "strokes"**,
   including on pages the user never opened. Fixed with hysteresis (seed +
   grow). **Control test: of the 18 pages never edited, 17 now yield zero
   components; the 18th correctly still yields the `danm14ad` pilot stroke.**
   Re-run this control after any threshold change.
2. **The length floor discarded real corrections.** `MIN_STROKE_PX` was 10 image
   px = 2.5 map px, so every 1–2 map px correction was thrown away as "a dot, not
   a line". The user named 9 notes that had been missed; all 9 had ink.

### Two tool bugs the third pass exposed

1. **`ingest` hardcoded `output/atlas/atlas_index.csv`.** A page must be read
   against the index of the **build it came from**, because the anchors include
   the green cross at the note's *current* corrected position, and that moves on
   every rebuild. Both `map_note_atlas.ingest` and `atlas_ink_debug.py` now
   prefer `<src>/atlas_index.csv`.
2. **`build --only` rewrote `atlas_index.csv` from just the rebuilt modules**,
   which would have truncated a 340-row index to 6 rows and made the other 88
   pages unreadable to ingest. It now merges.

### Atlas pass results

| pass | outcome |
|---|---|
| pilot (`danm14ad`, 2026-08-28) | read with no human help; 78,134 → 84,130 (7.2 px); verified in the live binary by byte search at VA `0x73C3E0` |
| first full read | 162 reads / 49 problems — **invalidated** by the phantom-ink bug |
| after hysteresis + merge | 167 reads / 15 problems |
| after the length-floor fix | **178 moves + 4 confirmations, 0 problems** |
| third pass (2 notes re-drawn) | `korr_m33ab` #14 179,153 → **179,148**; `korr_m36aa` #31 201,186 → **210,185** |

**Final: 250 corrections.** Validation clean — round-trip exact 250/250, inside
draw bounds 250/250, position key unique 250/250, 0 awaiting review.

The 4 confirmations (`kas_m25aa` #32, `tar_m02ab` #36, `tar_m05ab` #19,
`tat_m18ab` #50) each **reverted a live auto-correction back to vanilla**,
verified absent from `note_corrections.csv`.

`note_decisions.csv` was rebuilt from the pre-pass backup rather than edited in
place, so no stale rows survive.

**Floor check** (`atlas_validate_targets.py`): 161 on walkable floor, 21 off by
~1–4 map px — accepted, the 14×14 icon still covers floor. Largest:
`korr_m35aa` #53 ~3.8 px, `danm14ab` #21 ~2.5 px, `sta_m45ab` #3 ~2.5 px.

**Known wrinkle:** `korr_m33ab` #14 initially read as a 1-px move rather than a
confirmation because the user drew from the GREEN cross back down to the vanilla
marker — the nearest anchor is then the green cross and the tip lands 1 px off
vanilla. Outcome was right; it just spends a table entry where a `reject` would
spend none. Re-drawn explicitly in the third pass.

## Validation performed on every frozen list

- the new world position re-projects to **exactly** the intended map pixel,
  tested on the **float32** value the game will read back, not the float64
  intermediate;
- every correction lands inside the engine's own draw bounds;
- every corrected note's `(XPosition, YPosition)` key is **unique across all 340
  notes**, so a position-keyed table cannot move the wrong note.
