# FUTURE WORK, OPEN QUESTIONS, AND KNOWN LIMITS

Nothing here is required. Map-note placement is **closed and parked** at the
user's request. This is the list of what we would pick up if asked.

## Open questions (genuinely UNKNOWN)

| # | Question | What we know |
|---|---|---|
| 1 | Does anything read `MapZoom`? | Present in every `Map` struct, value **1** everywhere checked, **not** read by `0x578E00`. Low priority — no observed effect |
| 2 | Why does the `mainmenu*` GUI family report a flat 800×600 panel EXTENT regardless of bucket? | Never explained. Blocks finishing our own `generate_gui.py` rescaling for `mainmenu.gui` |
| 3 | What is the consequence of the **widened bound check** for the generic HUD path? | `0x578E9B`/`0x578EA6` were patched from 440/256 to 1760/853 for **all four callers** of `0x578E00`. The HUD path still produces 0..440 coordinates, so positions vanilla rejected are now accepted there. **Untested side effect, no observed symptom** |
| 4 | Why are the float twins `0x747748` / `0x7455D4` still vanilla while every integer twin is scaled? | KotorUniResPatch scales them and must temporarily restore them for the fog/grid overlay draw. **A real asymmetry, a real lead, and not investigated by us.** Candidate explanation for residual cosmetic oddities |
| 5 | Does the `.git`'s `GameVersion` field matter to the engine? | Or only to editor tooling. Safest practice already adopted: source the base `.git` from a real K1 extraction |
| 6 | Does KPM's runtime hooking actually work end-to-end on the packed Steam exe? | Never tested by anyone here. Release 0.6.0 claims it does; the author concedes at least one patch fails on Steam because init runs before the attach window |
| 7 | GPL implications of shipping our port of k1hrm's GPLv3 patcher | Must be resolved before publishing. See [SHIPPING](SHIPPING.md) |

## The orange-line question — the one live diagnostic thread

**Status: no longer reproducible in the shipped state**, because the box growth
that caused it was reverted. But the *original* observation predates that:
maps with grid over the unexplored area show an orange line at the right edge.

What we established:
- Across all 88 map textures the last drawn column (x=439) is **not** anomalous —
  largest deviation game-wide is `m01ab` at 17.0 mean, nothing above 20. So it is
  **not an art defect**.
- Therefore the orange is the **revealed map art showing through**, which points
  at the **fog/grid overlay that covers unexplored area not reaching the final
  column**.

If it is ever reported again on the reverted build, the discriminating
measurement is: **is the strip ~4 px wide (one map pixel at our scale)?** If so,
that pins it to a rounding-down in the overlay's width. Open question 4 above is
plausibly the same bug seen from the other side.

## Map-note placement — the known-imperfect edges, cheapest first

None of these is a bug; they are where the rules are knowingly approximate.

1. **`room_centre` uses the walkmesh centroid, not the room as drawn** (~35
   corrections; the largest remaining source of "not quite centred").
   Type specimen: Ebon Hawk Crew Quarters — the room **as drawn** spans x 116..138
   (centre **127**) while the walkmesh room `M12aa_01j` spans only x 122..138 with
   centroid x **131**, because bunks along the walls make the walkable floor a
   narrow off-centre strip. Using the full `.wok` (walkable + non-walkable faces)
   does **not** help: all-faces centroid is (130,107) vs walkable (131,108).
   **An art-based room centre is what's needed.** Vanilla was x 131, y 98 — so the
   fix already improved the vertical a lot and left the horizontal ~4 px off.
2. **`DOOR_NEAR_PX = 7` is deliberately tight.** The green-door rule only reaches
   a note already sitting on its door; a note misplaced 15 px from the door it
   marks is not reached at all. Widening is the obvious knob but **must be
   re-swept on crops first** — at 10 px the rule started pulling notes that were
   already correctly inside their room.
3. **Ambiguous doors pick the smaller room** (4–5 cases, all flagged and
   human-approved). Nothing better than "smaller = the named place" was found.
   A door's own orientation, or which side the note's name matches, may do better.
4. **Passage-named notes fall back to `room_centre`/no proposal** (3 cases: East
   Hallway B, North/South Corridor). Centring a note in the corridor it names is
   what item 1 would improve; two of the three are rejected anyway.
5. **The untouched tail**: 13 rejected, 75 below the 3 px threshold, 77 with no
   defensible proposal. Most of the 77 are large open areas where the room rule
   says nothing (Dantooine plains and the like). These need either a new ground
   truth or hand placement — the atlas round-trip is the tool for that and it
   works.
6. **`korr_m33ab`-style entries**: a stroke drawn *from the green cross back to
   vanilla* reads as a 1-px move rather than a `reject`, spending a table entry
   where none is needed. Cosmetically harmless; a rule could detect "tip lands
   within 1 px of vanilla **and** the matched anchor was the live cross" and
   convert it to a reject.

## Marker precision (open item 2 from the old list)

**There is a known, already-documented cause, and part of it is ours.** The note
path computes `round(k·(w−o)/s)`; the player/party path computes
`round(k·round((w−o)/s))` — it **rounds twice**. Measured difference over the 7
Ebon Hawk notes: **−2 to +1 px**. Our `PARTY_CAVE`/`PLAYER_CAVE` rescale the
already-rounded cached integer (`fild`/`fmul`/`fistp`), which *is* that second
rounding.

Vanilla A/B says vanilla is imprecise too, on both minimap and area map. So the
honest answer is **both**: an engine baseline plus ≤2 px of ours on top.

**The right fix, and where it belongs.** The KPM address DB named the writer:
**`CSWSAreaMap::SetPartyMemberWorldLocation` (0x5790C0)** — the *writer* of the
cached position whose *reader* (`0x5791B0`) we currently patch. KotorUniResPatch
independently confirms the approach: they never rescale a computed position, they
patch the bound constants *inside* the transform so the engine's own conversion
happens once in scaled space, and they hook `0x4B4E80` (`UpdateMapData`) purely
to guarantee the constants are in place **before the first marker plot fills the
cache**.

So: **get the cached position generated in scaled space instead of rescaling the
already-rounded integer.** Test against
`backups/swkotor.exe.pre-partyplayerfix-backup` (marker fix present, player/party
fix absent) at the same save and spot.

**Any change here MUST be checked against the HUD minimap** — this is the
subsystem that broke twice.

## Marker icon scaling (cosmetic, deliberately deferred)

Icons are hardcoded 14×14 / 20×20 and do not scale: **1.6 % of the map's height
where vanilla was 5.5 %.** Deliberately left until after placement so it does not
mask what is being corrected.

Two halves, and **we catalogued only one of them**:

1. draw-rect immediates — `0x694718` (`add eax,-0xa`), `0x69471F`
   (`mov eax,0x14`), `0x694762` (`mov eax,0xe`), plus the player (`-0x10`/32) and
   party (`-8`/16) equivalents;
2. **icon MATERIAL creation sizes** in the `CSWGuiMapHider` ctor (`0x693F60`):
   `0x69405B` = `0x20` (arrow), `0x6940DC` = `0x10` (circle), `0x69418F` = `0x14`
   (target/note). **Our exe still holds all three at vanilla.** Without this the
   draw-rect change only stretches a small texture.

**A better mechanism than patching each immediate** (steal the idea, not the
code): hook the four marker draw sites (`0x69473A`, `0x6949A7`, `0x694A6B`,
`0x694AD7`), reject rects wider/taller than 64 px, multiply w/h by the scale, then
`left -= (newW-oldW)/2` and `top -= (newH-oldH)/2` — **deriving** the centring our
immediates hardcode. One routine covers all four icon types.

**Caution:** our icon immediates and KotorUniResPatch's rect scaler are
**alternatives, not additions** — running both double-scales.

## The Area Map frame line — the only remaining route

The box may **not** be grown (F18). The only fix that does not disturb the map
render is **editing the art**:

`Override/lbl_map.tpc` is a k1hrm **2048×2048 DXT1** texture, 12 mipmaps.
A full DXT1 *encoder* is not needed — **a DXT1 block whose two colour endpoints
are equal decodes to a solid colour**, so the ~4×4 blocks covering the frame line
can be rewritten in place as solid background-colour blocks. **Only mip 0
matters** here (2048 → 2560 is magnification). The project already has a working
TPC reader.

Cost: moderate. Risk: it edits an asset the k1hrm GUI mod owns, so the original
must be backed up and the change documented, and a k1hrm reinstall would restore
the line.

**The alternative is architectural**: adopt KotorUniResPatch's integer-scale +
centred + `CSWGuiMapHider`-clipped model, which kills this whole artifact class by
construction (no fractional resampling ⇒ no edge smear, and the art stays
pixel-aligned with the map edge). **But the map would stop filling its box**
(3× = 1320×768 inside our 1760×853 box; 4× = 1760×1024 does not fit vertically),
undoing a confirmed fix. Not recommended without the user explicitly choosing
that trade.

## Other carried-over items

- **Blue transition lines with no note.** Vanilla content; our table can only
  *move* notes. Adding notes needs new waypoints with `HasMapNote=1`, i.e. the
  data-edit route, i.e. new-game-only. Worth quantifying first, which is now
  cheap: `map_art_lines.area_lines(area)` lists every drawn transition segment and
  we have every note position, so a sweep can report each segment with no note
  within N px. Decide only after seeing how many are missing.
- **Our own `generate_gui.py` covering everything k1hrm does.** Purely for the
  learning value; k1hrm's files already solve the practical problem. Blocked on
  open question 2.
- **HD map art.** If we ever ship it, KPM's `hud-minimap-map-size-fix-v1` is
  verified applicable — it makes the HUD minimap treat any atlas as logically
  512×256 by replacing `0x68ABF8: 8B 96 00 5E 00 00`.
- **Font size.** k1hrm documents "no font scaling available"; the *Larger Text
  Fonts* mod fills that gap at the cost of item stack counts (accepted).

## Porting to another KOTOR build

The addresses in [REVERSE_ENGINEERING](REVERSE_ENGINEERING.md) are for the
**Editable Executable** (FairLight pre-Steam-DRM v1.03), sha256
`761f9466f456a839…c49e9886` = KPM's `kotor1_cdcrack_103`.

- **GOG 1.03** and **CD-crack 1.03** are the builds KotorUniResPatch targets, and
  `0x578E00` matching ours strongly suggests the code layout is shared across
  them. But **their supported hashes are not our exe**, so re-verify every address
  before reuse.
- Free `.text` space is **not guaranteed** to match across builds — our cave
  depends on a 3,485-byte zero tail at `0x73C263`. Measure it, don't assume it.
- The **packed Steam exe cannot be statically patched at all** (`.text` entropy
  8.00). Only runtime injection reaches it.
- `hires_patch.py` already carries per-build offset tables (gog / 4cd-ITA /
  4cd-POL / macOS) inherited from k1hrm, and refuses to patch a build whose
  current bytes don't match the expected defaults. That refusal is the right
  behaviour — keep it.
- The KPM address DB covers `kotor1_0_3` and independently confirms our function
  boundaries name-for-name; query it before hand-deriving anything on a new build.

## Supporting another resolution

Nothing special is required. `hires_patch.py` computes its constants from the
target resolution (`width*(440/640)`, `height*(256/480)`):
2560×1600 → 1760/853 · 2560×1440 → 1760/768 · 3840×2160 → 2640/1152 ·
3440×1440 → 2365/768 — all far inside the int16 operand range (the ~11,900 px
width ceiling is not reachable by any real display).

**The note table is unaffected** — it stores world coordinates, upstream of the
entire resolution chain. Re-run the widescreen patcher; leave the table alone.

The one caveat: marker icons are hardcoded 14×14, so **the higher the resolution
the smaller they read**, which makes the optional icon-scaling work more valuable
at 4K than at 1600p.
