# ARCHITECTURE — how KOTOR's map and GUI systems actually work

Everything here was derived from disassembly, Unicorn emulation, live x32dbg
capture, or in-game observation. Where a claim is inference it says so.

## 1. The two layers of the resolution problem

Do not conflate these. Discovered the hard way (2026-08-23):

1. **Engine-level resolution gate.** `swkotor.exe` hardcodes which resolutions
   it will accept. CONFIRMED by test: with **zero** Override files and
   `swkotor.ini` set to 2560×1600, the Options menu still clamped to 800×600.
   This is baked into the exe; no `.gui` file can change it.
2. **GUI-layout scaling.** Once the engine accepts a resolution, each `.gui`
   file still needs correct per-control positions for it.

Layer 2 is pointless to test until Layer 1 is unlocked. CONFIRMED directly:
dropping a generated `mipc_2560x1600.gui` into `Override/` did nothing
observable, because `mipc*.gui` only affects the in-game HUD.

There is also a **third, separate limitation** that appears only after the gate
is open: the engine's 2D GUI/camera system bounds itself with hardcoded
**±640 / ±480** constants (the base 640×480 canvas), so all 2D UI renders
correctly-proportioned but confined to a small unstretched box in the top-left.
This is what k1hrm's `hires_patcher.pl` exists to fix, and what our
`tools/hires_patch.py` ports.

### GUI resolution buckets

The game ships pre-authored GUI layouts for exactly **4 hardcoded 4:3
resolutions**, and the families behave differently:

| Resref family | Panel EXTENT behaviour |
|---|---|
| `mainmenu8x6 / 10x7 / 12x9 / 16x12` | all report a flat **800×600** panel EXTENT regardless of name — **UNKNOWN why** |
| `mipc8x6 / 10x7 / 12x9 / 16x12` (in-game HUD) | panel EXTENT correctly matches the named resolution |

Single-resolution screens (`saveload`, `inventory`, `journal`) are authored at a
plain **640×480** panel; `container` (a popup) at **305×327**. CONFIRMED by
extracting from `data/gui.bif`.

The engine's own runtime anchor implementation was found during disassembly:
`shift = ((actual_dimension - 640) / 2)`, each guarded by a flags-byte test
(`test byte ptr [ecx+0x44], 0x20` for X, `0x40` for Y). That is very likely the
engine's generic version of the same start/end/center/stretch anchor concept
`tools/rescale.py` independently reverse-engineered from position data alone.
INFERRED (the correspondence), CONFIRMED (the instruction pattern: a whole-exe
scan found exactly 3 matches for 640 and 3 for 480, all already known).

## 2. The Area Map coordinate pipeline

This is the core model. **CONFIRMED — reproduced bit-for-bit against a
live-captured calibration object.**

```
.are "Map" struct
   MapPt1X/Y, MapPt2X/Y      (normalised 0..1 fractions)
   WorldPt1X/Y, WorldPt2X/Y  (raw world coordinates)
   NorthAxis, MapResX, MapZoom (sint32)
        |
        v  ARE loader (0x509C50..0x50A050)
   MapPt_scaled = round(MapPt_fraction * 440.0 | 256.0)      <- rounding is REAL
   WorldPt passed through raw (no fmul, no rounding)
        |
        v  constructor 0x578C60, 12 arguments
   scale  = (WorldPt1 - WorldPt2) / (MapPt_scaled1 - MapPt_scaled2)   -> obj+0x18 (X), obj+0x1c (Y)
   offset = WorldPt1 - scale * MapPt_scaled1                          -> obj+0x20 (X), obj+0x24 (Y)
        |
        v  transform 0x578E00 (CSWSAreaMap::GetMapPixelFromWorldCoord)
   apply NorthAxis axis map to the query position
   pixel = int((v - offset) / scale + 0.5)     per axis
   bound check: 0 <= X <= 0x6e0, 0 <= Y <= 0x355   (patched 1760/853)
        |
        v  screen
   screen = box origin + pixel        (box = LBL_Map's EXTENT)
```

**NorthAxis (`obj+0x10`) applies an axis swap/negation** before offset/scale, on
both the query position **and** on `WorldPt` when the calibration is derived:

| NorthAxis | X source | Y source |
|---|---|---|
| 0 | X | Y |
| 1 | −X | −Y |
| 2 | Y | −X |
| 3 | −Y | X |

CONFIRMED by model selection over the whole game — count how many of the 340
notes survive the engine's own bound check:

| model | notes rejected |
|---|---|
| H0 — no NorthAxis anywhere (the project's original model) | 9 / 340 |
| H1 — NorthAxis in the transform only | 57 / 340 |
| **H2 — NorthAxis in the transform *and* applied to `WorldPt`** | **1 / 340** |

H0 and H2 coincide for NorthAxis 0 and 1 (the pure negation cancels), which is
why nothing broke on the Ebon Hawk. Distribution across the 90 modules with
notes: NorthAxis 0→72, 1→6, 2→4, 3→8. **48 notes live in NorthAxis 2/3 areas**;
a tool built to the old spec silently produces garbage for all of them.

Independently re-confirmed in game by the Phase 1a test, which moved notes to
known corners in modules with NorthAxis 0 (`m14ad`), 1 (`m16aa`) and 3 (`m01aa`)
and saw them land where asked.

A third, cheap confirmation: rendering `danm13` (**NorthAxis 3**) places every
gameplay object inside the enclave's walkable art — a visual check that the axis
map is right, and one that immediately showed the placement problem too
("To Outer Courtyard" correctly on the map transition, while "Ebon Hawk",
"Aratech Mercantile" and "Jedi Council Chamber" are all off-centre from what
they name).

### Storage convention vs xoreos

Ours stores `scale = ΔWorldPt / ΔMapPt` and consumes it with `fdiv`; xoreos
stores `ΔMapPt / ΔWorldPt` and multiplies. Same math, opposite convention — the
two models agree, they do not contradict.

### The invariance that makes the resolution patch work

Rescaling `MapPt_scaled` uniformly by `k` gives `scale' = scale/k` while
**`offset' = offset` is exactly invariant** — the `k` cancels in the offset term.
Since the transform divides by scale, the computed pixel scales by exactly `k`.
CONFIRMED to float32 precision by emulation, and this is precisely why the
notes fix works by copying the calibration object and dividing only the two
scale fields.

## 3. The shared calibration singleton — the trap that cost two builds

**There is exactly ONE `Map` calibration object per area, and both the HUD and
the Area Map read it.** CONFIRMED three ways:

1. **Live x32dbg**: hardware breakpoints on `obj+0x18`/`+0x1c` fired 100+ times
   during plain HUD gameplay with the Area Map never opened.
2. **Object identity**: `ecx == 0x052117E8` in every context — HUD-only
   gameplay, pause menu, and Area Map open.
3. **Structural**: both paths resolve the object through the *same* global
   chain, `[0x7a39fc] → [+8] → call 0x4AE6B0 → [+0x218]`. That is stronger than
   the breakpoint evidence, because it proves they *must* coincide rather than
   that they happened to.

The reach is through a **generic, panel-agnostic per-frame dispatcher**:

```
0x4BABB0   generic per-screen update (no static callers at all — reached only
           through a runtime-computed function pointer; proven by a whole-file
           absolute-value scan finding 0 references)
  -> 0x4B4E80   CServerExoAppInternal::UpdateMapData
    -> marker-position-setter cluster 0x5790C0 .. 0x579313
      -> 0x578E00   the transform
```

Two different intermediate chains land on the same `+0x218`:
- notes: `[0x7a39fc] → [+8] → call 0x4AE6B0 → [+0x218]`
- player/party: `[0x7a39fc] → [+4] → call 0x5ED8B0` then `call 0x4B14F0 → [+0x218]`

`0x4B14F0` is a generic memoised lookup and `0x5ED8B0` a two-hop getter; neither
is panel-discriminating. CONFIRMED by full disassembly. So there is **no
HUD-vs-AreaMap gate anywhere in this chain** — which is why "redirect the shared
constant" can never work, and why the fix had to be a private *copy* of the
object handed to one call site.

### The disjointness that makes the copy safe

`0x578C60` writes two unrelated field groups from **disjoint** argument slots
(CONFIRMED by Unicorn emulation with one argument perturbed at a time):

| slots | fields | consumer |
|---|---|---|
| 1 | `+0x04`, `+0x08`, `+0x0c` | grid array/count/dim — read by the HUD via `0x579090` |
| 2 | `+0x10` | NorthAxis |
| 11 | `+0x14` | a float |
| {3,5,7,9} | `+0x18` **and** `+0x20` together | X scale + offset |
| {4,6,8,10} | `+0x1c` **and** `+0x24` together | Y scale + offset |
| 0 | (nothing) | the literal `1` the loader pushes |

"Both fields move together for any one of 4 slots" is the **signature of a
two-point linear calibration**, not "one input feeds scale, another feeds
offset" as originally assumed.

## 4. Two different marker pipelines

This asymmetry matters and is easy to get wrong.

| | Map notes | Player / party markers |
|---|---|---|
| when computed | **fresh, per draw**, inside the Area Map's own loop | **once per frame**, by the generic dispatcher, into a cache |
| path | `0x6946F4 → 0x578E00` with a calibration object | `0x5790C0` writes `[struct + 0x28 + i*4]` (X) and `+0x34` (Y) |
| read for drawing | the transform's own output | `0x5791B0` (`GetPartyMemberMapLocation`) — a pure cache read, **does not call `0x578E00`** |
| rounding | `round(k·(w−o)/s)` | `round(k·round((w−o)/s))` — **rounds twice** |
| our fix | private rescaled calibration copy | rescale the cached integer at the read site |

The double-rounding costs **−2 to +1 px** (measured over the 7 Ebon Hawk notes).
That is our own contribution on top of vanilla's own imprecision. The right fix
is to make the *writer* (`0x5790C0`) produce scaled values, not to rescale the
already-rounded integer at the reader — see [FUTURE_WORK](FUTURE_WORK.md).

`0x5791B0` in full (thiscall, `ecx` = party struct, first stack arg = index):

```
eax = [ecx+4]                 ; party count, return 0 if <= 0
edx = index                   ; return 0 if edx >= 3
eax = [ecx + edx*4 + 0x28]    ; X  -> caller's [esp+0x14]
eax = [ecx + edx*4 + 0x34]    ; Y  -> caller's [esp+0x18]
return 1
```

Both call sites then do `X-8/Y-8` (party, 16×16 icon) or `X-0x10/Y-0x10`
(player, 32×32) and draw at that rect — definitively the on-screen position.

## 5. The map artwork

- Texture name: **`lbl_map<areaResRef>`** (e.g. `lbl_mapm12aa` for `ebo_m12aa`),
  in `TexturePacks/swpc_tex_gui.erf`. **97 of them**, one per area. (Not a
  contradiction with the "88 distinct textures" figure elsewhere: 97 exist in the
  ERF across all areas; 88 distinct ones are used by the 90 modules that have
  notes, because two module pairs share art.)
- **512×256**, of which the engine draws only the **left 440×256**; the
  remaining 72 columns are power-of-two padding. CONFIRMED, and independently
  corroborated by KotorUniResPatch calling it "the vanilla 440x256 area-map
  basis".
- **Stored bottom-up — flip vertically before sampling.** Getting this wrong
  produced a spectacular false positive: 68 "misplaced" notes that were purely
  an artifact of the flip.
- `map.gui`'s `LBL_Map` has an **empty `BORDER.FILL`** in both vanilla and our
  Override copy — the texture is bound by engine code from the area resref, not
  by the `.gui`. This was a red herring that cost a session; the convention was
  discoverable in one step by listing the ERF's resrefs.
  **Lesson: grep the game's own containers before researching a naming
  convention externally.**

### Art ↔ marker registration is EXACT

The hypothesis that the art might be misaligned with the marker space
(k1hrm's own "Known Issue #4") was tested two independent ways and **refuted**:

1. **Object point cloud.** 71 positioned non-note objects in `ebo_m12aa.git`
   that must lie on walkable floor: **87.3 % land on floor art with zero shift**.
   Best translation over ±120 px is (+8, 0) at 67/71; best affine (scale ±8 %,
   shift ±16 px) is 70/71 at sx=1.04, sy=0.96. Marginal scans are flat and noisy
   (85.9–93 %) with **no coherent peak** — no systematic error.
2. **Texture ground truth.** Predicted on-screen art bbox from the texture
   (left 440 of 512) = box-local x 412..1356 / y 10..840; **measured on the real
   screenshot = 412..1357 / y 13..844.** Agreement to ~1–3 px out of 1760.

The art and the markers occupy exactly the same 440×256 space and the patch
scales both by the same `kx`/`ky`.

## 6. Map notes as data

- Map notes are **waypoints** in the module's `.git` `WaypointList` with
  `TemplateResRef = sw_mapnote001` — dedicated, single-purpose UI anchors, not
  gameplay waypoints reused for pathing. That is what made editing their
  position defensible.
- **`HasMapNote`, not `MapNoteEnabled`, decides whether a note renders.**
  CONFIRMED: `ebo_m12aa` has **33** waypoints with `MapNoteEnabled=1` but only
  the **7** with `HasMapNote=1` draw, and those 7 match the live-captured
  addresses exactly. `MapNoteEnabled` is set on ordinary `sw_waypoint001`
  objects too.
- The display name is a **strref** (`MapNote`, a CExoLocString) resolved through
  `dialog.tlk`.
- Scope, measured: **340 notes across 90 modules.** 339 render; 1 does not.

### Identity keys — what is and is not safe

| key | safe? | why |
|---|---|---|
| **world (XPosition, YPosition) float32 pair** | **YES** | all 340 are distinct game-wide, zero collisions. This is what the exe table keys on |
| strref | no | 39415 appears twice in one module (PortQuarters and Starboard both display "Crew Quarters") |
| tag | no | `sw_exit` appears twice in `ebo_m12aa` |
| waypoint ordinal | no | breaks under any other mod's waypoint edits, and the save's cached copy reorders them |
| per-area calibration | no | `ebo_m12aa` and `ebo_m41aa` share **identical** `MapPt`/`WorldPt` |

### The Ebon Hawk's five module instances

`ebo_m12aa`, `ebo_m40aa`, `ebo_m40ad`, `ebo_m41aa`, `ebo_m46ab`. CONFIRMED:
`ebo_m40aa` and `ebo_m40ad` have **no map notes at all**; `ebo_m46ab` has 1
unrelated note; only `ebo_m12aa` (7) and `ebo_m41aa` (7) matter. They share
identical calibration but their note positions differ slightly (Engine:
Y = 7.279 vs 8.410), i.e. they were hand-placed independently and each needs its
own table row.

## 7. Save-game caching (decides delivery mechanism)

CONFIRMED offline and then in game:

- `SAVEGAME.sav` is an **ERF** containing one `<module>.sav` per visited module;
  each holds `<area>.git` + `<area>.are` + `Module.ifo`.
- The cached `.git` **carries the map notes at their exact vanilla positions**.
- The cached copy is keyed by the **area** resref (`m12aa.git`) and its
  `WaypointList` ordering **differs** from the module's own `.git` (Engine Room
  is index 26 in the save, 51 in the module) — it is re-serialised live state,
  not a file copy. Any save-patching idea cannot reuse module note indices.
- Only the **current planet's** modules are cached (one save had 8; no Taris
  modules survived) — consistent with discarding a planet you cannot return to.

**Precedence, answered in game:** a `.git` in `Override/` **does** reach a module
already visited and cached — but shadowing a module resource makes the engine
**discard the whole cached module state** and reload the module fresh. Map
exploration fog reset in both test areas, which implies containers, corpses,
enemies and trigger flags reset too. The game also crashed once (single
occurrence, unproven cause, heavily-patched exe — hold loosely, but it is
disqualifying either way).

That is why the delivery mechanism is an **exe-side table**: it serves existing
saves and new games identically, touches no game data, and leaves nothing in
saves. See [FIX_IMPLEMENTATION](FIX_IMPLEMENTATION.md) and
[archive/PHASE1A-TEST.md](archive/PHASE1A-TEST.md) for the full experiment.

## 8. Why placement must be somewhere the player actually goes

`danm16`'s "Holding Cell" was moved to px(30,230) and was **provably** written
there (forensics on the save) yet was **invisible in game**. That target is 24.5
world units from the nearest room — a corner of the map the player never enters.
By contrast the Endar Spire target, also on black unmapped art, *was* visible.

**So black artwork is not the problem; being outside the region the player ever
reaches/reveals is.** This is why every clamp rule must land on the nearest
**walkable floor inside the map**, not on a raw map edge.
