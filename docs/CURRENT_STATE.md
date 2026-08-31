# CURRENT STATE — what is live, what works, what must not be touched

Last updated **2026-08-29**. Authoritative check: `python tools/state.py`, which
reconstructs the applied state from the binary and the CSVs, so it is right even
if this file goes stale.

## Install

| item | value |
|---|---|
| Game | `C:\Program Files (x86)\Steam\steamapps\common\swkotor` |
| Live exe | md5 `435108fdb65bac2151ab694e7fb8e36a`, **4,050,944 bytes** |
| Resolution | 2560×1600 (`swkotor.ini`), fullscreen |
| `Override/` | **600 files** (k1hrm GUI set + cosmetic mods — see [manifest](#override-manifest)) |
| Base exe lineage | UniWS-patched "KOTOR Editable Executable" (FairLight-cracked pre-Steam-DRM v1.03), **not** the packed Steam exe |
| DPI | `~ HIGHDPIAWARE` in `HKCU\...\AppCompatFlags\Layers` — **still required** |
| `steam_appid.txt` | present in install root (content `32370`) — **leave it**, the non-Steam-launched exe needs it |

The exe size grew from the historical 4,042,752 B because `pe_space.py` appended
8 KB. Notes written before 2026-08-29 quote the old size; both are correct for
their date.

## What is applied to the binary

| what | address | size | status |
|---|---|---|---|
| UniWS resolution gate | see [FIX_IMPLEMENTATION](FIX_IMPLEMENTATION.md#layer-1) | — | CONFIRMED in game |
| 640/480 canvas constants + list-click fix | 6 negative-offset sites | — | CONFIRMED in game |
| `mapscale` (Area Map fills its box) | 17 int16 sites | — | CONFIRMED in game |
| Private float redirect (minimap fix) | operands at `0x6944A8`/`0x6944C4` → `0x78CC00`/`0x78CC04` | 12 B | CONFIRMED in game |
| notes-calibration cave | `0x73C1D0` | 60 B | CONFIRMED in game |
| party marker cave | `0x73C20C` | 38 B | CONFIRMED in game |
| player marker cave | `0x73C232` | 49 B | CONFIRMED in game |
| marker hook | `0x6946D3` → `0x73C1D0` | 5 B | CONFIRMED |
| **note-table match routine** | **`0x73C270`** | **57 B** | CONFIRMED in game |
| **note correction table** | **`0x86D010` .. `0x86DFB0`** | **250 × 16 B** | CONFIRMED in game |
| note-table hook | `0x6946EF` → `0x73C270`, resumes `0x6946F4` | 5 B | CONFIRMED |
| reserved region (extended `.rsrc`) | `0x86D000`, 8 KB, magic `K1MAPNTS` | 8176 B usable = 511 entries | CONFIRMED |

`.text` free tail remaining after the caves: `0x73C2A9`..`0x73D000`. The table no
longer lives there — see [FIX_IMPLEMENTATION](FIX_IMPLEMENTATION.md#pe-section-space).

## In-game confirmation (user, 2026-08-29)

> "area map and minimap are unchanged, player and party markers are fine. New map
> notes position are okay"

That closes every `CLAUDE.md`-required check on the 250-entry build: in-menu Area
Map, HUD minimap, and player/party markers unmoved. **Map-note placement is
CLOSED and parked** at the user's request — revisit only if they ask.

## Solved and confirmed

- 2560×1600 resolution, HUD anchoring, menus filling the screen
- Tactical Area Map fills its box and is centred
- List-clicking (save/load, inventory, equip, journal, skills/powers/feats)
- HUD minimap renders (was black)
- Area Map player/party markers track correctly
- Area Map map-note markers: 250 corrections live

## Known limitations and accepted trade-offs (won't fix unless asked)

| item | verdict | evidence |
|---|---|---|
| Thin light-blue frame line on the Area Map's top/left/right | **Accepted.** A 1-px border baked into the `lbl_map` panel art, magnified ~4× | measured; two fix attempts reverted — see [failures](EXPERIMENTS_AND_FAILED_APPROACHES.md#f18) |
| Item stack-count number missing | **Accepted (won't fix).** Caused by the third-party *Larger Text Fonts* mod: glyphs 68 % taller, baseline 0.15→0.32, so digits no longer fit the engine's fixed badge | A/B proven with `tools/font_test.py` |
| Marker icons don't scale with resolution (14×14 / 20×20 hardcoded) | Cosmetic. 5.5 % of map height in vanilla → 1.6 % at 2560×1600 | CONFIRMED by disassembly + measurement |
| Player marker slightly imprecise | **Present in vanilla too**, on minimap and area map. Our patch adds ≤2 px of double-rounding on top | vanilla A/B, 2026-08-28 |
| Some blue transition lines have no note | Vanilla content. Our table can only *move* notes, never add one | vanilla A/B |
| Stutter for ~2 s after closing the Area Map | **Present in vanilla. Not ours. CLOSED** | vanilla A/B |
| Area Map frame has no bottom border | Vanilla art has none either; only visible because our map fills the box | vanilla A/B screenshot |
| One note never draws (`tat_m18ac` "Star Map") | **User chose vanilla invisibility** over an inaccurate edge marker | user decision, recorded in `note_decisions.csv` |
| 21 corrected targets sit 1–4 map px off walkable floor | Accepted — the 14×14 icon still covers floor | `atlas_validate_targets.py` |

## Do NOT change casually

1. **`LBL_Map`'s EXTENT (380, 393, 1760, 853) in `Override/map.gui`.** Growing it
   in *any* direction makes the engine smear the map texture's last row/column
   across the extra pixels. Tried twice, reverted twice.
   See [failures](EXPERIMENTS_AND_FAILED_APPROACHES.md#f18).
2. **The shared float constants `0x747748` (440.0) and `0x7455D4` (256.0).**
   Rewriting them in place breaks the HUD minimap. Redirect the *consumer's*
   operand to a private copy instead. This is the pattern that generalises.
3. **The three marker caves at `0x73C1D0` / `0x73C20C` / `0x73C232`.** Verified,
   working, and confirmed in game. The note table deliberately uses its own new
   hook at `0x6946EF` so it never touches them.
4. **`note_corrections.py finalize` is the gate.** Run it after touching *any*
   rule — it is the only thing that re-derives table keys from the real module
   files and re-checks round-trip, bounds and key uniqueness.
5. **`output/atlas-annotated-2026-08-29/`** (72 annotated pages) and the two
   re-drawn pages in `output/atlas-updated/` are **source data**. The ingest is
   re-derivable in seconds; the user's ink is not.
6. **Game data stays untouched.** No `.git`/`.are` in `Override/`, no `.mod` in
   `modules/`. The Phase 1a test proved a data edit resets a visited module's
   cached state in an existing save.

## Backups and reverts

All backups live in `backups/` only — enforced by `tools/backup_paths.make_backup()`;
`backup_paths.assert_clean(game_dir)` checks the rule.

| to undo | restore |
|---|---|
| note table only (keeps the PE extension) | `backups/swkotor.exe.pre-notetable-backup.20260829-215022` |
| note table + PE extension | `backups/swkotor.exe.pre-pe-extend-backup` |
| everything back to pre-note-table | `backups/swkotor.exe.pre-notetable-backup` |
| the player/party marker fix only | `backups/swkotor.exe.pre-partyplayerfix-backup` |
| both marker fixes | `backups/swkotor.exe.pre-markerfix-backup` |
| to 100 % vanilla (exe + Override + ini) | `python tools/vanilla_toggle.py vanilla`, back with `restore` |
| `map.gui` frame experiment | `backups/map.gui.pre-mapframefix-backup` (already restored) |

Vanilla for the toggle = `backups/swkotor.exe.steam-backup` (md5
`06b34d1b8a1ecefbaad0bf5e26556c71`, the **packed** Steam original: `.bind`
section, `.text` entropy 8.00) + empty Override + 1600×1200.

## Data source of truth

| file | what |
|---|---|
| `output/note_corrections.csv` | the **250** corrections the live table is built from |
| `output/note_decisions.csv` | **201** reviewer decisions (178 override, 13 approve, 10 reject) |
| `output/map_note_proposals.csv` | the automated proposal pass, 340 rows |
| `output/atlas-annotated-2026-08-29/` | the user's hand annotations (72 pages with ink) |
| `output/atlas-updated/` | the approved atlas, 90 PNGs + `atlas_index.csv` (340 rows) |
| `output/note_corrections.pre-atlas-2026-08-29.csv` | the 175-entry table before the atlas pass |
| `output/note_corrections.applied-169.csv` | an earlier build, for comparison |
| `output/map_notes.csv` | the raw survey: every note in the game with map pixel, drawn/not, distance to nearest object, art underneath |
| `output/note_review.csv` | the triage worklist — which proposals need human eyes |
| `output/mapnotes/*.png`, `output/mapnotes-proposed/*.png` | per-module renders (current, and before/after) |
| `output/review-sheets/`, `output/review-sheets-r2/`, `output/review-crops/` | contact sheets from the two review passes |
| `output/git-edits/phase1a/` | the three `.git` edits used in the save-caching test (`m14ad.git`, `m16aa.git`, `m01aa.git`) |
| `reference/kpm/kotor1_0_3.db` | third-party symbol DB keyed to our exe (9,711 functions) |

## Regenerate end-to-end (deterministic)

```
python tools/map_note_propose.py propose output/map_note_proposals.csv
python tools/note_corrections.py finalize output/note_corrections.csv
python tools/note_table_patch.py plan  "<exe>"      # dry run, always
python tools/note_table_patch.py apply "<exe>"
```

Atlas round-trip: `map_note_atlas.py build <outdir>` →
(user annotates) → `map_note_atlas.py ingest <dir> [--write]` → `finalize` → `apply`.

## The shipped patcher (`patcher/`, Phase 2, 2026-08-30)

What a player runs. Applies **all five layers in one pass** to one in-memory
image and writes the exe once, in the order that reproduces the confirmed build:
mapscale + private floats → map-note marker cave → party/player caves →
`pe_space` → note table.

```
python patcher/install.py [GAME_FOLDER] [--dry-run]   # Apply.bat
python patcher/revert.py  [--force]                   # Revert.bat
python patcher/selftest.py                            # the acceptance test
```

- **Resolution is read out of the exe, never asked** (`0xB6C7`/`0xBA6C` = −width,
  `0xB6DA`/`0xBA83` = −height, cross-checked against `0xAA65`/`0xAA85`), and
  `Override/map.gui`'s `LBL_Map` must equal `(95·kx, 118·ky, 440·kx, 256·ky)`
  ±1 px, so a `.gui`/exe resolution mismatch is refused instead of shipped.
- **Gates:** size must be 4,042,752 (the Editable Executable after UniWS+k1hrm);
  all 16 map-scale sites at vanilla defaults; four hook sites at their original
  bytes; caves zero; no `K1MAPNTS` region. Already-applied → exits clean;
  half-applied → refuses and says to revert.
- **Post-write verification (21 checks)** re-reads from disk, re-disassembles the
  match routine with capstone, and asserts **no byte outside the declared ranges
  changed** — a chunked before/after diff, so a bad offset cannot pass silently.
- **The note table ships frozen** (`patcher/data/note_table.bin`, 250 entries,
  4,000 B, sha256 `880a325d…`) rather than re-derived from the player's modules.
  `tools/freeze_note_table.py [--check]` regenerates it from
  `output/note_corrections.csv` + the real module files and fails on drift.
- **Backup + manifest never go in the game folder, and since 2026-08-31 not in
  the mod folder either** — `%LOCALAPPDATA%\K1AreaMapFixes\` holds
  `backup/swkotor.exe.original` and `installed.json` (sha256 before/after,
  resolution, every offset touched), because the mod folder is a download and
  people delete downloads. `manifest._data_home()` resolves it: `K1AMF_HOME`
  wins outright; a **development checkout keeps using `patcher/`** (marked by
  `selftest.py`, which never ships, so the paths above still hold in this repo);
  an install recorded in an older release folder keeps using that folder.
  `last-run-log.txt` stays next to `Install.bat` — `manifest.visible_home()`.
- Nothing of k1hrm's or UniWS's is bundled or reimplemented; `tools/uniws_patch.py`
  and `hires_patch.patch()` remain dev-only.

**Acceptance test, re-runnable:** `patcher/selftest.py` patches the official-chain
exe and requires md5 `435108fdb65bac2151ab694e7fb8e36a` — byte-for-byte the exe
confirmed in game — plus six refusal/revert cases. Any change to a written byte
or to layer order fails it.

## Phase 3 — automated QA (done 2026-08-30)

    python tools/qa.py --json output/qa_report.json

**PASS, 49/49 resolutions.** Builds the official-chain test binary at every one
of k1hrm 1.5's 49 resolution sets (enumerated from disk, 800×600 to
15360×8640) — official UniWS artifact → official k1hrm at that resolution →
our layer — then runs `patcher/k1amf/verify.py:check`'s 20-check battery plus
the `Override/map.gui` box check against a fresh read from disk. Separately
proves the note-table position-key scheme collision-free across **all 340**
map notes in the game, not just the 250 corrected ones (`tools/note_corrections`
builds its uniqueness table from every note before filtering to corrections),
and that the shipped frozen table matches a fresh re-derivation
(`tools/freeze_note_table`). k1hrm's dialogue letterbox is off in this run,
matching the live confirmed exe; letterbox-on is Phase 4's gap (§2.9). Full
spec: [`PHASE3_SPEC.md`](PHASE3_SPEC.md); report at `output/qa_report.json`.
Not covered here: the K1CP key-survival test, moved to Phase 5.

## Override manifest

KOTOR 1's `Override/` has **no subfolder support** (unlike K2) — everything flat.
600 files, no filename collisions between sources:

| Files | Source |
|---|---|
| 81 `.gui` | k1hrm 1.5, `16-by-10/gui.2560x1600/` |
| 2 (dialogue font) | Larger Text Fonts, `Dialogue_Description_VeryBig/` |
| 6 (menu font) | Larger Text Fonts, `Menu_Big/` — downgraded from VeryBig because `savefont16x16b` overflowed save-slot hitboxes; `pfont16x16b*` deliberately left at VeryBig |
| 2 (name font) | Larger Text Fonts, `Names_VeryBig/` |
| `DP_K1MenuBack.tga`, `mainmenu.mdl/.mdx` | K1 Main Menu Widescreen Fix v1.2 |
| `logo_sw_02.tpc` | same, `OPTIONAL/Vanilla Logo - Upscaled/` |
| 44 | HD UI Menu Pack "Pure Vanilla Edition" v1.1 |
| 270 `.tga` | Pretty Good! Icons for KotOR 1.0 |
| 150 `.tpc` | HD PC Portraits v1.0 |
| 20 `.tpc` | HD NPC Portraits v2.0 |
| 10 + 9 `.tga` | Random HD UI Elements v1.0 (Party Selection + Planet Icons) |

`*_p.gui` files bundled with the font mod were **excluded** — they are
vanilla-resolution (305×327) reference copies and would regress those screens.

The `.gui` files exclude nothing else; `Override/lbl_map.tpc` (2048×2048 DXT1) is
part of the k1hrm/HD set and owns the Area Map background art.
