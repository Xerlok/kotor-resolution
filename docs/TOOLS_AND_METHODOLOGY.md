# TOOLS AND METHODOLOGY

## Our tools (`tools/`, plus a few at the project root)

### Binary patching

| tool | what it does |
|---|---|
| `hires_patch.py` | The main widescreen patcher — our Python port of k1hrm's GPLv3 `hires_patcher.pl`. Canvas ±640/±480 constants, the list-click pair, `patch_map_scale()`, `redirect_bigmap_floats()`, `add_area_map_marker_fix()`, `add_party_player_marker_fix()`. Verify-before-write throughout; refuses to patch if current bytes ≠ expected vanilla defaults |
| `uniws_patch.py` | Our port of UniWS's resolution-gate patch, from `patches.ini` |
| `apply_marker_fix.py` / `apply_party_player_marker_fix.py` | Standalone **incremental** appliers. Deliberately NOT wired into `patch()`'s pipeline, which expects a vanilla exe |
| `note_table_patch.py` | `plan` (dry run) / `apply` (patch + readback verify) for the note table. Re-derives every table key from the real module `.git` |
| `pe_space.py` | `plan` / `apply` — reserves table space by growing the last PE section. Idempotent via a `K1MAPNTS` magic |
| `state.py` | **Reconstructs what is applied straight from the binary and the CSVs.** Run this first in any session; it is right even when the docs are stale |
| `vanilla_toggle.py` | `status` / `vanilla` / `restore` — deterministic 100 % vanilla round trip (exe + Override + ini) |
| `backup_paths.py` | `make_backup` / `backup_path` / `assert_clean` — enforces "no backup in the game folder" in code |
| `font_test.py` | `off` / `on` / `status` — parks the *Larger Text Fonts* group as one unit. The reusable "is it the font mod?" harness |
| `map_frame_fix.py` | **Kept for its measurements and root-cause write-up. Do NOT apply.** See [failures F18](EXPERIMENTS_AND_FAILED_APPROACHES.md#f18) |

### Analysis

| tool | what it does |
|---|---|
| `disasm_helpers.py` | `refs` / `disasm` / `func` / `calls` (capstone + pefile). `calls` includes a **drift-immune brute-force `E8`+rel32 scan** |
| `emulate_map_ctor.py` | Unicorn harness: runs `0x578C60` in isolation with controlled inputs to map which argument feeds which output field |
| `map_calibration.py` | **The authoritative model.** NorthAxis-aware calibration from any `.are`, `world ↔ map pixel` both ways, map-texture loading (flip + 440-crop), `dialog.tlk` strrefs. **Its module docstring is the canonical write-up — read that rather than reconstructing.** Runs standalone to dump one module |
| `map_geometry.py` | Per-room walkable floor in world coords; seeking KEY/BIF reader |
| `map_art_lines.py` | Reads door (green) / transition (blue) segments out of the map artwork; PCA orientation, normal, anchors |
| `gff.py` / `gff_writer.py` / `keybif.py` | Format readers/writers |
| `rescale.py` / `compare_guis.py` / `generate_gui.py` | The anchor-inference GUI rescaler (see below) |
| `inspect_gui.py` / `list_guis.py` | Archive exploration (project root) |

### Map-note pipeline

`map_note_survey.py` (`survey` / `render` / `renderall` / `target`) ·
`map_note_propose.py` (`propose` / `render` / `renderall` / `residuals` / `show`) ·
`map_note_review.py` (`triage` / `crops` / `sheets`) ·
`note_corrections.py` (`finalize` / `summary`) ·
`map_note_atlas.py` (`build` / `ingest`) ·
`atlas_ink_debug.py` · `atlas_validate_targets.py` · `make_git_edit.py`

### Self-tests

`roundtrip_test.py` (GFF write → byte-identical for `mainmenu.gui`) and
`selftest_rescale.py` (reconstructs real `mipc16x12` positions from `mipc8x6` +
the learned model with **0 px error** across 133 modelled controls).

## Third-party tools and libraries

| tool | used for | notes |
|---|---|---|
| **capstone** | disassembly | the workhorse |
| **keystone** | assembly | every injected instruction is keystone-assembled — **no hand-encoded ModRM** — then independently re-disassembled with capstone and checked instruction-by-instruction against the design |
| **pefile** | PE parsing | |
| **unicorn** | isolated-function emulation | see the harness gotchas below |
| **x32dbg** (x64dbg project, 32-bit build) | live debugging | at `downloads/x64dbg/release/x32/x32dbg.exe`. 32-bit because `swkotor.exe` is. Used interactively; **never scripted** — worth scripting the attach/breakpoint setup if live sessions become routine |
| **PyKotor** 2.3.12 | ERF/RIM/GFF/TPC read-write | a deliberate exception to "build it ourselves" — verified end-to-end against the real install before trusting |
| **numpy** 2.5.2 | vectorised pixel/array work | installed 2026-08-29 |
| **Pillow** | image measurement and rendering | |
| **sqlite3** | the KPM address DB | |
| **UniWS** | resolution gate | patch signature verified byte-for-byte before use |
| **k1hrm 1.5** | the `.gui` set + the patcher we ported | GPLv3, read in full |

### Reference implementations (read, not used at runtime)

- **xoreos** — clean-room Odyssey reimplementation. `kotorbase/area.cpp`,
  `kotor/gui/ingame/minimap.cpp`. Confirmed the `Map` struct has a
  `WorldPt1/2` pair, and that scale/offset derive from the **ratio** of
  `MapPt1/2` to `WorldPt1/2` rather than a fixed-constant multiply. It documents
  the map quad as 512×256 with world↔map calibration. It never implemented a full
  Area Map screen, so it cannot settle runtime object sharing.
- **reone** — implements minimap and full Area Map as two **rendering modes of one
  shared `Map` object**, both calling the same `getMapPosition()`:
  architecturally the same shared-calibration problem we hit. It derives map-pixel
  scale from the live texture's dimensions at render time rather than a hardcoded
  constant, which is consistent with why our downstream operand redirect worked
  and the upstream one did not.
- **xoreos-tools** — `gff2xml`/`xml2gff`, `unrim`/`unerf`/`unkeybif`,
  `convert2da`. Useful as an independent cross-check of our own parsers.
  Never pursued.
- **KGE / Visual KotOR GUI Editor** — drag-and-drop `.gui` editor with
  bounding-box preview. Considered for the (since-refuted) "Known Issue #4"
  layout question. Last visible activity ~2022; some UI colours reportedly
  hardcoded.

## Technique notes and traps

### Function boundary identification

**`disasm_helpers.py func`'s "nearest prologue" heuristic has produced at least
three false positives** in this binary:

| claimed | actually |
|---|---|
| `0x6933A0` contains `0x6946F4` | it's a short unrelated function ending `ret 8` at `0x693596`; the real container is **`0x6943D0`** |
| `0x4B4960` is the caller of `0x5790C0`/`0x5792D0` | it's `CServerExoAppInternal::ResolvePlayerByFirstName`; the real one is **`0x4B4E80`** |
| `0x694822` is a function start | it's a coincidentally-matching prologue byte pattern **inside** `0x6943D0` — there are **zero `ret`s** between `0x6943D0` and `0x6946F4` |
| `0x508C50` starts the ARE loader | false positive; the real span is `0x509C50`–`0x50A050` |

**Always verify by disassembling forward from a candidate start and checking for
an intervening `ret`.** This is not bad luck: a published survey found
prologue/pattern-scan false-positive rates from **28 % to 99.99 %** depending on
tool. A stronger signal from the same source: **trust addresses that are actual
call/xref targets over bare prologue matches.**

Also: **disassembling from an unaligned offset decodes garbage-but-plausible
instructions** for a stretch before re-syncing with the real byte stream. One such
call produced a confident, wrong reading of `0x694660`–`0x69469F`.

### Identify code by what it references, not by where it sits

The method that works: search `.text` for references to a **constant's address**,
then identify each referencing function by the **GUI tag strings it binds** and by
its callers/vtable. That gave a definitive HUD-vs-AreaMap answer in one pass,
after adjacency reasoning had produced a wrong one (F7).

### Static caller searches have a hard limit

`disasm_helpers.py calls` does both a linear scan and a brute-force `E8`+rel32
scan (immune to disassembly drift). Both are correct and both were insufficient:
they answer "who calls X **directly**". They cannot see a dependency reached
through a generic dispatcher, and `0x4BABB0` has **zero static references
anywhere in the file** — proven by a whole-file 4-byte absolute-value scan, so it
is reached only via a runtime-computed function pointer. "Called once per screen
vs iterated over every resident panel" **cannot be answered by more static work**.

### x32dbg

- Run the game **windowed** before attaching — a paused exclusive-fullscreen
  surface can become unrecoverable.
- Disable **Options → Preferences → Events → TLS Callback** (and DLL Load/Unload)
  or attach re-breaks on every DLL load.
- `bphws`'s size argument must be a **digit** (`1`/`2`/`4`/`8`), not a word:
  `bphws ecx+18, r, 4`. The GUI route (right-click register → Follow in Dump → Go
  to → Expression → select bytes → Breakpoint → Hardware, Access → Dword) always
  works and needs no syntax.
- x86 caps at **4 hardware breakpoints** total (DR0–DR3); the address must be
  aligned to the size.
- **The default Call Stack view walks the EBP chain and is unreliable here** —
  several functions set up no frame, and it showed a plausible-looking but wrong
  2–3-frame chain. Enable **"Show suspected call stack frame"** (right-click) for
  a full-stack scan, or cross-check by hand.
- Breakpoint-then-backtrace is exactly what Cheat Engine's "find what
  writes/accesses this address" automates — the approach is sound, not a reason to
  switch tools.

### Unicorn harnesses

Three gotcha categories, all of which this project hit: unmapped memory
dependencies, uninitialised registers, missing stack setup.

Two specific lessons from `emulate_map_ctor.py`:

1. **Hook at the right depth.** The allocator was hooked at `0x6FD8CF` (the CRT
   allocator itself) rather than stubbing `0x6FA7E6`, so `0x6FA7E6`'s own real
   stack-cleanup code still runs and **no calling convention had to be guessed**.
2. **Degenerate inputs produce false signals.** The first run used a uniform
   baseline (all args = 2) and reported "every argument affects everything" —
   every subtraction resolved to `0/0`. Giving each of the 12 argument slots a
   **distinct** baseline gave a clean, unambiguous map.

### Live-capture discipline

From the three x32dbg map-note captures (raw logs kept in `downloads/`):

- Capture what you asked for, then **check the register's meaning at that exact
  instruction.** `add esi,0x90` ran *before* both breakpoints, so `ESI` already
  pointed at `note+0x90`; a dump of `esi+0x90` was actually `note+0x120` and its
  all-zero contents nearly became a false conclusion.
- **Capture the whole window, not cherry-picked offsets.** Dumping `esp` to
  `esp+0x34` in one go is what settled which slots held the transform's output.
- Corroborate across sessions: capture #3's calibration decoded to
  scaleX 0.076325 / scaleY −0.096452 / offsetX −16.7252 / offsetY 85.7785,
  matching capture #2 from the previous day to 4 decimal places — good evidence
  the object is read consistently, not stale or drifting between draws.
- Bring the dump back and compute by hand rather than interpreting live.

### The GUI anchor model

`rescale.py` classifies each control axis as `start` / `end` / `center` /
`stretch`-anchored plus a fixed leftover-pixel correction, learned from the same
file at two known resolutions (`mipc8x6` → `mipc16x12`). This independently
rediscovered what the engine itself does at runtime
(`shift = ((actual_dimension - 640) / 2)` guarded by a per-control flags byte).

### Research

- **Read the upstream project's own documentation first, alongside the source.**
  This is how the list-click bug was actually found (F5), and it is a saved
  memory for all projects.
- **Grep the game's own containers before researching a naming convention
  externally.** The map-texture naming convention (`lbl_map<areaResRef>`) was
  discoverable by listing one ERF's resrefs; a session was spent blocked on web
  research for it.
- Research agents are useful but **not authoritative**: the save-caching claim
  that redirected the whole project came from two agents and was wrong (F17).
  Treat agent output as a lead to test, not a fact.

## Workflow discipline (from `CLAUDE.md`, earned from incidents)

1. **Dry-run (`plan`) first, then `apply`. Re-disassemble what is on disk** rather
   than trusting the write.
2. **Back up first** — `backup_paths.make_backup()` copies into `backups/`,
   md5-verifies, reuses an identical existing backup, and **timestamps rather
   than overwriting** when the name is taken by different content. That overwrite
   would have silently destroyed a last-known-good exe.
3. **After any patch, verify BOTH the in-menu Area Map and the HUD minimap.**
   The minimap is the subsystem that broke twice.
4. **If a patch regresses another subsystem, revert to the last known-good build
   and document the root cause** — don't stack fixes.
5. **Bisect a multi-part patch by group early**, rather than treating it as one
   atomic on/off switch.
6. **Look at the rendered picture before trusting a placement heuristic.**
7. Every patcher writes its backup via `backup_paths`; `assert_clean(game_dir)`
   fails loudly if artefacts creep back into the install.
