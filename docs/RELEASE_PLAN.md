# RELEASE PLAN — shipping and QA

Written **2026-08-30**. **Scope narrowed the same day by user decision** — see §0.
Nothing has been implemented; this is awaiting approval to start.

Evidence labels follow [README](README.md): **CONFIRMED** / **INFERRED** /
**UNKNOWN**. They are load-bearing — several items are deliberately recorded as
untested so the release notes cannot overclaim.

Plain-language twin: [RELEASE_PLAN_SIMPLE.md](RELEASE_PLAN_SIMPLE.md).

---

## 0. Scope — decided 2026-08-30

**We ship only what we built ourselves: the Area Map layer.** The widescreen
resolution work is delegated to the tools that already do it.

**Product name: "K1 Area Map Fixes". One mod, one patcher** (user decision).
**Licence: GPLv3** (user decision) — see §0.3.

### 0.1 In scope

| what | layer | origin |
|---|---|---|
| Area Map fills its box at the target resolution | `mapscale` (17 int16 sites) | ported from k1hrm's disabled branch |
| HUD minimap keeps working while it does | private-float redirect, `0x78CC00`/`0x78CC04` | **ours** |
| Note markers land correctly | private rescaled calibration copy, cave `0x73C1D0` | **ours** |
| Player + party markers land correctly | caves `0x73C20C` / `0x73C232` | **ours** |
| 250 map-note position corrections | match routine `0x73C270` + table `0x86D010` | **ours** |
| Marker icon size | — | **ours, deferred to 1.1** |

### 0.2 Out of scope — prerequisites, not our work

| what | who does it |
|---|---|
| Engine resolution gate | **UniWS** |
| ±640/±480 GUI canvas + list-click fix | **k1hrm** (`hires_patcher`) |
| Dialogue letterbox proportion | **k1hrm** — `LETTERBOX_SCALE` is a required argument to its patcher and defaults to on. CONFIRMED by reading `hires_patcher.pl`. Never ours; drop it entirely. |
| First-cutscene bottom letterbox bug | ShaeMyName's K1 Ultrawide Letterbox Fix (DS #2993) |
| Menus, fonts, main menu, GUI/icon/portrait packs | existing community mods |

`tools/uniws_patch.py` and `hires_patch.patch()` **remain dev tools** — they are
how we build test binaries — but they are not shipped and their defects
(`assert`-based validation, the 1024-vs-1600 interface bucket divergence) stop
being release blockers.

### 0.3 Licence — RESOLVED

Ship under **GPLv3**, crediting ndix UR. `patch_map_scale()` is a port of
k1hrm's GPLv3 `hires_patcher.pl` (the `mapscale` branch they wrote and shipped
hardcoded off), and it is the only in-scope component with GPL lineage; the
marker caves and note table are wholly original. Copyleft costs a free KOTOR mod
nothing. **This closes the item that had blocked publication since 2026-08-28.**

### 0.4 What this scope change bought us

- The patcher shrinks to: fingerprint → backup → `mapscale` + private floats →
  three marker caves → `pe_space` → note table → verify readback.
- The publication blocker is gone (§0.3).
- The interface-bucket and letterbox gaps leave the critical path.
- **A new, better install design becomes possible** — see §5.1.

### 0.5 Dropped from the 2026-08-29 plan, recorded so it is not re-proposed

The earlier draft shipped a full widescreen bundle: our UniWS port, our canvas
port, the letterbox, and a two-release split (note table standalone, then the
bundle). All of that is superseded by §0.1/§0.2. The *findings* behind it remain
valid and are kept in §2. Nothing in `docs/` was deleted.

---

## 1. Current state

### Live install — CONFIRMED 2026-08-30

Verified by `python tools/state.py` plus direct byte reads:

- 2560×1600, exe md5 `435108fdb65bac2151ab694e7fb8e36a`, 4,050,944 B.
- Install clean: no `.git`/`.are` in `Override/`, no `.mod` in `modules/`, no
  backups in the game folder.
- All five layers live and confirmed in game; CSV ↔ binary agree at 250
  corrections and 201 reviewer decisions.

### Gaps that block shipping, at the new scope

| gap | evidence |
|---|---|
| ~~**No one-shot patcher.**~~ **CLOSED 2026-08-30 (Phase 2)** | `patcher/install.py` applies all five layers in one pass and writes the exe once; `patcher/selftest.py` proves the result is byte-identical to the confirmed build. |
| ~~**No exe build fingerprint**~~ **CLOSED 2026-08-30 (Phase 2)** | the patcher gates on size (4,042,752), on all 16 map-scale sites holding vanilla defaults, and on four hook sites holding their original bytes; sha256 before/after goes in `installed.json`. |
| ~~**Never tested on an exe patched by the *official* tools**~~ **CLOSED 2026-08-30** | ~~every in-game confirmation to date is on an exe built by *our ports* of UniWS and k1hrm.~~ Half-wrong as written: the UniWS half was always the official GUI tool, and our k1hrm port turns out to be byte-identical to official k1hrm. The official chain rebuilds the live exe exactly — §2.9. |
| **Marker icon sizes still vanilla** | `0x69405B`/`0x6940DC`/`0x69418F` = `0x20`/`0x10`/`0x14`. Deferred to 1.1. |
| **`state.py` / `vanilla_toggle.py` hardcode this machine's Steam path** | correct for dev tools; must not ship. |
| ~~**No version control**~~ **CLOSED 2026-08-30 (Phase 0)** | `git`-tracked, pushed to the private `github.com/Xerlok/kotor-resolution`. |

### Tooling

Present: numpy 2.5.2, Pillow, capstone, keystone, pefile, PyKotor, sqlite3,
x32dbg. **Missing and needed: `pytest`, `PyInstaller`.**

---

## 2. Findings from the 2026-08-30 inspection

All **CONFIRMED** by measurement. Re-derivable by walking
`downloads/k1hrm-1.5/*/gui.*/` and parsing with `tools/gff.py`.

### 2.1 k1hrm 1.5 covers every target resolution

**49 resolution sets, 81 `.gui` files each** — 4:3, 16:9, 16:10, 21:9, 32:9,
including 1920×1080, 2560×1440, 3840×2160, 1920×1200, 2560×1600, 3840×2400,
2560×1080, 3440×1440, 3840×1600, 5120×2160, 3840×1080, 5120×1440.

At the new scope this matters more, not less: k1hrm *is* the prerequisite, and it
covers everything we want to support.

### 2.2 `LBL_Map` matches our `mapscale` formula at every resolution

In **46 of 49** sets, `LBL_Map` EXTENT is exactly
`(95·kx, 118·ky, 440·kx, 256·ky)`, `kx = w/640`, `ky = h/480`. The three
exceptions differ by 1 px of rounding and none is a target: 1400×1050
(width 963 vs 962), 2880×1800 (top 443 vs 442), 960×720 (left 143 vs 142).

So `patch_map_scale()` reproduces k1hrm's box **by construction at every
resolution**. This generalises the 2560×1600-only evidence in
[F10](EXPERIMENTS_AND_FAILED_APPROACHES.md#f10) and is the core correctness
argument for the whole release.

### 2.3 The minimap box is fixed at every resolution

`LBL_MAP` in `mipc16x12.gui` is **(6, 6, 512, 512) in all 49 sets**. Previously
known only for the four vanilla buckets. Confirms across the whole range why
rewriting the shared constants had to break the minimap
([F6](EXPERIMENTS_AND_FAILED_APPROACHES.md#f6),
[F8](EXPERIMENTS_AND_FAILED_APPROACHES.md#f8)) and why the private-float redirect
is correct everywhere. k1hrm ships all four `mipc` buckets in every set.

### 2.4 No rounding divergence at any target resolution

Python's `round()` (banker's) and Perl's `int(x+0.5)` agree on all 13 targets.
1400×1050 (`440·kx = 962.5`) proves the divergence is real for arbitrary
resolutions — a **latent 1-px bug**, harmless today. Use `floor(x+0.5)`.

### 2.5 Area-map aspect stretch, measured

The art is stretched horizontally by exactly `kx/ky`: 1.00× at 4:3, 1.20× at
16:10, 1.33× at 16:9, **1.79× at 21:9, 2.67× at 32:9**. Markers scale by the same
factors so registration stays exact — correct, but increasingly distorted.
Inherited from k1hrm's box shape, not introduced by us.

### 2.6 Exe variants available locally

| file | size | md5 | sections |
|---|---|---|---|
| `downloads/swkotor.exe` | 4,042,752 | `d2bc3d8ef527df1b8547bc0740db74ed` | 4 |
| `backups/swkotor.exe.uniws-only-backup` | 4,042,752 | `ce852f515d56d521b3a94b6e34250a88` | 4 |
| `backups/swkotor.exe.steam-backup` | 4,395,008 | `06b34d1b8a1ecefbaad0bf5e26556c71` | 5 (`.bind`) |

**No GOG and no retail 4-CD binary here.** WSGF states both are directly
patchable — **researched, not verified by us**, and must be labelled so.

### 2.7 Our layer applies cleanly on top of the official tools — **CONFIRMED 2026-08-30 (Phase 1)**

**Promoted from INFERRED to CONFIRMED by byte-level reproduction.** See §2.9 for
the evidence. The original reasoning below was correct in every particular.

Reasoned from documented behaviour, **not yet tested end to end** *(at the time
of writing; now tested — §2.9)*:

- k1hrm ships `mapscale` hardcoded off, so its 17 int16 sites and the two shared
  floats `0x747748`/`0x7455D4` are still at vanilla defaults after official
  k1hrm runs → layer 3 applies.
- Our hooks (`0x6946D3`, `0x694A42`, `0x694AB1`, `0x6946EF`), caves from
  `0x73C1D0`, and private float slots from `0x78CC00` are untouched by both
  tools → layers 4 and 5 apply.
- Official k1hrm applies **both** halves of the list-click offset pair; the
  dropped-pair bug was in our port only ([F5](EXPERIMENTS_AND_FAILED_APPROACHES.md#f5)).

~~**Promoting this to CONFIRMED is Phase 1's job.**~~ — done, §2.9.

### 2.9 Phase 1 result: the official chain reproduces the live exe byte-for-byte — CONFIRMED 2026-08-30

Reproducible end to end; every claim here is a measurement, not a reading.

**The headline: the whole supported chain rebuilds the live, in-game-confirmed
exe exactly.** From `backups/swkotor.exe.uniws-only-backup` → official
`hires_patcher.pl 2560 1600 no` → `patch_map_scale` → `apply_marker_fix` →
`apply_party_player_marker_fix` → `pe_space apply` → `note_table_patch apply`
yields md5 **`435108fdb65bac2151ab694e7fb8e36a`**, 4,050,944 B — an **exact
match** for the live exe in `docs/CURRENT_STATE.md`.

Consequences, in order of importance:

1. **Risk #2 is closed.** The binary confirmed in game *is* an official-chain
   binary. The in-game evidence we already have transfers to the supported path
   without re-testing; no fresh Tier A pass is needed at 2560×1600 to establish
   this (Tier A still runs in Phase 4 for the *other* resolutions).
2. **Our k1hrm port is byte-identical to official k1hrm.** Patching the same
   UniWS base at 2560×1600, letterbox on, official `hires_patcher.pl` and
   `tools/hires_patch.py` produce **0 differing bytes** — the same 23 bytes over
   11 sites (`0xAA65`, `0xAA85`, `0xB6C7`, `0xB6DA`, `0xBA6C`, `0xBA83`,
   `0x2928B3`, `0x2928C3`, `0x292959`, `0x29296B`, `0x355788`). [F5](EXPERIMENTS_AND_FAILED_APPROACHES.md#f5)'s
   dropped-pair bug is genuinely fixed: both halves of each pair are written.
3. **The UniWS half was never our port to begin with.** `staging/swkotore.undo1-4`
   and `swkotorc.undom1-2` are official `uniws.exe` undo records — plain text,
   e.g. `undo1` = offsets 2034789/2034799 over 800/600 — created beside the file
   the GUI tool patched. `staging/swkotor.exe` == `backups/swkotor.exe.uniws-only-backup`
   is that artifact, on the **1600×1200 interface** entry. `tools/uniws_patch.py`
   exists only to build the 1024-bucket test variant and never produced a
   shipped binary. So §2.7's worry only ever applied to the k1hrm half.
4. **The `.gui` half is pure official k1hrm too.** All **81** files of
   `16-by-10/gui.2560x1600/` are byte-identical to the live `Override/`
   copies — including `map.gui`. No `map_frame_fix` residue survives; the two
   reverted `LBL_Map` resize attempts left nothing behind.

**Two corrections to this document, found while measuring:**

- **§0.2's "LETTERBOX_SCALE … defaults to on" is imprecise.** In
  `hires_patcher.pl` the argument is required and *any* value not starting with
  `f`/`n`/`0` turns it on — but the shipped `hires_patcher.bat` wrapper offers
  `0` as its default answer, so a user pressing ENTER gets letterbox **off**.
  It is also forced off at exactly 4:3.
- **"17 int16 sites" is 16 on our build.** `find_map_matches` matches
  `map_projection_offsets_x` (1) + `map_offsets_x` (7) + `map_offsets_y` (8) =
  **16**. The 17th, `map_grid` @ `0x17906F`, holds `1401` in *vanilla* — that
  offset belongs to a different exe build, so it never matches and has never
  been written, on the live exe or any test build. Harmless, but the count
  should say 16 (+1 build-specific site that does not apply here).

**The one thing Phase 1 did *not* confirm: the letterbox.** The live exe was
built with letterbox **off**; the only delta between it and a letterbox-on build
is 3 bytes at `0x355788` (`b96ddb` → `6edbb6`). §4's published install order
tells users to answer **YES**, which is therefore a configuration **no one has
run in game**. It is k1hrm's own feature and affects dialogue letterbox
proportion only — not the Area Map — so the risk is low, but it is untested and
must not be described otherwise. Decide in Phase 4 whether to recommend YES,
recommend NO, or test one dialogue scene with YES.

### 2.10 Findings from building the patcher (Phase 2, 2026-08-30)

**`map_grid` at `0x17906F` has never been patched, in any build.** It is one of
the 17 int16 sites in `hires_patch.MAP_OFFSETS`, but it holds **1401** in the
pristine `downloads/swkotor.exe`, not the 32 the table expects — so
`find_map_matches()` has always skipped it. Verified against the untouched exe,
the UniWS-only backup and the official-chain exe. The offset belongs to a
different exe build; it came over with `hires_patcher.pl`'s per-build offset
lists. **The exe confirmed in game was therefore built with 16 sites written,
not 17**, and the patcher now requires exactly 16 and treats a matching
`0x17906F` as an unknown build (`detect.SKIP_SITES`) rather than writing a byte
this project has never tested. Not a bug to "fix": correcting the offset would
change bytes in a subsystem whose only evidence is the live build.

**§2.4's latent rounding bug is fixed.** `patch_map_scale()` used Python's
banker's `round()`; it now uses `hires_patch._round_half_up()` = Perl's
`int(x+0.5)`. Byte-identical at every target resolution (the acceptance test
proves it at 2560×1600); the difference only appears at 1400×1050, one of
k1hrm's 49 sets, where `440·kx = 962.5` and k1hrm's own `.gui` box says 963.

**Three small refactors to verified tools**, all covered by
`tools/verify_official_chain.py` still reproducing md5 `435108fd…`:
`pe_space.extend(data)` (the header edits, on a bytearray, so the patcher writes
the same bytes rather than reimplementing them); `note_table_patch.layout()`
(one definition of where the routine and table go); and `map_calibration` now
imported lazily inside `load_corrections()`, so the patcher can import
`note_table_patch` without PyKotor.

### 2.8 The Ultrawide Letterbox Fix is complementary

DS #2993 fixes a **branching bug** (the first letterbox after an area load skips
the call that sets up the bottom bar, pushing subtitles off-screen) — distinct
from k1hrm's letterbox *proportion*. It instructs users to install last, which
contests our own "last" rule; byte-range overlap with our hooks is **UNKNOWN**
and must be checked. Its packaging shape (frozen patcher + Apply/Revert `.bat` +
Python source, need not live in the game folder) confirms
[SHIPPING](SHIPPING.md)'s recommendation is current practice as of mid-2026.

---

## 3. Resolution test matrix

Our patch is resolution-parameterised, so the matrix stays — but the checklist
shrinks to what is actually ours.

Hardware constraint: one 2560×1600 panel. Anything larger needs **Nvidia DSR or
AMD VSR**. Enable it before Tier A.

### Tier A — full manual pass. Only these may be called "tested".

| resolution | aspect | why |
|---|---|---|
| 2560×1600 | 16:10 | our reference; already confirmed |
| 1920×1080 | 16:9 | most common target |
| 3440×1440 | 21:9 | flagship ultrawide; where the stretch question bites |
| 3840×2160 | 16:9 4K | largest common; where icon size is worst |

### Tier B — smoke pass

2560×1440 · 1920×1200 · 2560×1080 · 5120×1440 (32:9) · **1600×1200 as the 4:3
control** — the only configuration where `kx ≈ ky`, so the only one that catches
a regression masked by anisotropic scaling.

### Tier C — "supported, untested"

The remaining ~40 k1hrm sets. Declared offline-verified only, in those words.

### Per-resolution manual checklist — now 5 items

Menus and lists are no longer ours. Item 3 is mandatory; the minimap is the
subsystem that broke twice.

1. Area Map **fills its box**, centred
2. Area Map note markers sit on their rooms
3. **HUD minimap renders** (not black)
4. Player + party markers track while walking
5. Open and close the Area Map repeatedly — no crash, no corruption

### Automated per-resolution checks (all 49, no game needed)

Against a copy patched at each resolution:

- `Override/map.gui`'s `LBL_Map` equals the patched `map_offsets_x`/`_y`
- shared floats `0x747748`/`0x7455D4` still read 440.0 / 256.0
- operands at `0x6944A8`/`0x6944C4` point at `0x78CC00`/`0x78CC04`
- every int16 write in range
- note table round-trips byte-identical; all 340 notes resolve as intended

A working prototype of the box check exists from the 2026-08-30 session.

---

## 4. Compatibility test matrix

The top two rows changed status: they are now **required prerequisites**, not
peers.

| mod | class | relationship | status | test |
|---|---|---|---|---|
| **UniWS** | exe | **REQUIRED** | CONFIRMED | test against the official tool, not our port |
| **k1hrm 1.5** | exe + `.gui` | **REQUIRED** — our `mapscale` targets its box | CONFIRMED across 49 sets (§2.2) | precondition check + official-tool test |
| KOTOR Editable Executable | exe replacement | required on Steam | CONFIRMED | baseline |
| **K1CP 1.11** | data (HoloPatcher) | if it moves a note, our key stops matching → their fix wins | **ASSUMED, unverified** | decisive test below |
| **K1 Ultrawide Letterbox Fix** | exe patcher | complementary (§2.8); also claims "last" | byte range UNKNOWN | range check + in-game |
| True Controller Support | `dinput8.dll` ASI | process-level, no static overlap | INFERRED | launch + play |
| **KPM / KotorUniResPatch** | runtime DLL | **alternative, not addition — double-scales** | CONFIRMED by address comparison | declare incompatible; confirm the failure mode |
| **Flawless Widescreen** | runtime memory injection (Lua plugin, live process) | **different mechanism from our whole stack — not a static file/exe change, nothing on disk to detect or gate against** | INFERRED — WSGF itself recommends UniWS+k1hrm for K1, not FWS (FWS is their K2/TSL recommendation) | declare incompatible / not supported, same posture as KPM; do not attempt interop (same class of problem as the deferred ASI item, §7) |
| 4 GB patch / no-CD patchers | exe / PE header | may collide with `.rsrc` growth or the `Hellspawn Reborn` watermark ([F19](EXPERIMENTS_AND_FAILED_APPROACHES.md#f19)) | INFERRED | apply-both test |
| HD UI Menu Pack, Pretty Good! Icons, HD portraits, Main Menu Widescreen Fix | Override art | no shared ground | CONFIRMED | none |
| **KOTOR Widescreen Fade Fix** | Override art/texture | no shared ground (fade transition asset only) | INFERRED | none |
| **3440x1440 Enhanced HUD/UI and Menus** | Override `.gui`/texture | **may touch `map.gui`, which k1hrm's per-resolution set also owns — unchecked** | UNKNOWN | check whether it ships/edits `map.gui`; if so, treat as k1hrm-set replacement, not an addition |
| Larger Text Fonts | Override fonts | kills item stack counts | CONFIRMED, accepted | document only |

### The K1CP test worth building

Install K1CP into a throwaway copy, then run `note_corrections.py finalize` — it
re-derives every table key from the **real module files**. Any key that stops
matching is exactly a note K1CP moved. Turns "we assume graceful degradation"
into a number, and re-runs free on every future K1CP release.

### Published install order

```
Editable Executable (Steam only)
  -> swkotor.ini
  -> UniWS
  -> k1hrm            <- our prerequisite; answer YES to its letterbox prompt
  -> K1CP + content mods
  -> K1 Area Map Fixes  (ours)
  -> Ultrawide Letterbox Fix
```

Byte ranges to publish so a collision is diagnosable by someone who is not us:
hooks `0x6946D3`+5 and `0x6946EF`+5; caves `0x73C1D0`–`0x73C2A9`; reserved
`.rsrc` region at `0x86D000` (8 KB, magic `K1MAPNTS`); private floats
`0x78CC00`–`0x78CC0F`.

---

## 5. Installation recommendation

**HoloPatcher cannot do this** — CONFIRMED: GFF/2DA/TLK/SSF/NSS only, never the
executable. Ship the community-standard shape (§2.8): a frozen Python patcher +
`Apply.bat` / `Revert.bat`, **source shipped alongside**, SHA-256 published for
both, **`--onedir` not `--onefile`** (onefile is a known AV heuristic trigger and
we already have a second one in `pe_space`).

### 5.1 Auto-detect the resolution — the design the new scope unlocks

**Do not ask the user for their resolution. Read it out of the exe.**

k1hrm's patcher writes `-width` / `-height` into the canvas constants that were
vanilla `-640` / `-480`. CONFIRMED on the live exe: offsets `0xB6C7`/`0xB6DA`
read `-2560` / `-1600`.

So the patcher can:

1. Read those offsets → the exact resolution k1hrm was run at.
2. If they still read `-640`/`-480`, **k1hrm has not been run** — refuse with
   that exact message.
3. Cross-check `Override/map.gui`'s `LBL_Map` against
   `(95·kx, 118·ky, 440·kx, 256·ky)` for that resolution → proves the matching
   `.gui` set is installed too.

Two independent checks, zero questions asked, and it structurally eliminates the
most common failure mode in this whole mod category: a mismatch between the
resolution in the exe, the `.gui` set, and `swkotor.ini`. **This is the single
highest-value feature in the release.** The `.gui` check code already exists.

### 5.2 Other requirements

1. **One entry point.** Fingerprint → backup → `mapscale` + private floats →
   three marker caves → `pe_space` → note table → verify readback. Every step
   already refuses on unexpected bytes; the pipeline needs assembling.
2. **Fingerprint and refuse unknown builds**, naming the Editable Executable,
   rather than probing for free space. GOG and 4-CD ship as "untested; the
   patcher refuses if bytes don't match" — honest and safe given §2.6.
3. **Backups + manifest.** JSON manifest (exe hash before/after, resolution,
   patch list, cave ranges) beside the patcher; `Revert.bat` restores from it.
   "Never in the game folder" is a *development* rule; for players the patcher's
   own folder is natural, and DS #2993's precedent says it needn't live in the
   game folder at all.
4. **Bundle nothing of k1hrm's.** Require and detect.
5. **Troubleshooting doc:** Steam "verify integrity" deleting the swapped exe;
   `~ HIGHDPIAWARE`; AV false positives with published hashes; "k1hrm not
   detected"; and how to change resolution later (re-run UniWS + k1hrm from
   stock, then re-run ours — our pipeline gates on vanilla defaults by design).

---

## 6. Map-note / icon scaling — deferred to 1.1

**They do need to scale.** A 14 px icon was **5.5 %** of the map's height in
vanilla, is **1.6 %** at 2560×1600 and **1.2 %** at 3840×2160; in map-space terms
it shrinks as `1/ky`. [F13](EXPERIMENTS_AND_FAILED_APPROACHES.md#f13)'s confirmed
mechanism — the *slop* is invariant, the *icons* changed.

**The HUD minimap needs no icon scaling — CONFIRMED.** Its box is a fixed
512×512 at all 49 resolutions (§2.3), so the icon is the same fraction of it
forever. All five draw sites and all three material sizes live inside
`CSWGuiMapHider` (`0x693F60`) and `0x6943D0`, both Area-Map-owned, so **this
class of change structurally cannot repeat the minimap regression**.

**Design: patch the immediates, not a new generic hook.**

- `s = clamp(round(min(kx, ky)), 1, 8)`. `min` keeps icons **square** — `kx`
  would stretch them 2.67× at 32:9; integer keeps materials on clean multiples.
- **Material sizes, non-optional:** `0x69405B` → `32s`, `0x6940DC` → `16s`,
  `0x69418F` → `20s`. Without these the draw-rect change only stretches a small
  texture.
- **Draw-rect immediates in matched pairs:** `0x69471F` (20 → 20s) with
  `0x694718` (−10 → −10s); `0x694762` (14 → 14s) with its −7 partner.

Immediates beat KotorUniResPatch's generic rect hook because
[F9](EXPERIMENTS_AND_FAILED_APPROACHES.md#f9) already *proves* half-size centring
is exact at any size — the derivation the hook buys is a property we have
confirmed we do not need. No hook, no cave, no new failure mode.

**Prerequisites:** three sites are uncatalogued (the unselected note's −7, and
both player `−0x10`/32 and party `−8`/16 draw-rect immediates); and it is
**UNKNOWN** whether the materials are procedural or resampled textures — a larger
material could read blurry. Check visually at `s=3` first.

**Never combine with KPM's rect scaler** — they double-scale.

---

## 7. Executable variants — scope answer

**`dinput8.dll` / ASI runtime injection and packed-Steam-exe support are a future
project.** For it: roughly doubles the audience, and it is the one thing a static
patcher fundamentally cannot do (Steam `.text` entropy 8.00, decrypted only in
memory). Against it, decisive for now: it changes the deployment contract, and
[F24](EXPERIMENTS_AND_FAILED_APPROACHES.md#f24) established our cave asm is
parameterised on the table's absolute VA, which a memcpy-style REPLACE hook
cannot relocate. That is a rewrite, not a port.

---

## 8. Major risks

| # | risk | severity | mitigation |
|---|---|---|---|
| 1 | **No version control.** 32 MB of irreplaceable atlas ink, one disk. | **highest** | `git init` first; `.gitignore` the 336 MB `backups/`. |
| 2 | ~~**Never tested against the official UniWS + k1hrm chain** (§2.7). That is now the *only* supported path.~~ **CLOSED 2026-08-30 by Phase 1** — the official chain rebuilds the live in-game-confirmed exe byte-for-byte (§2.9). | ~~high~~ **closed** | Done. Residual: the letterbox-on configuration is still unrun in game (§2.9). |
| 3 | **GOG / 4-CD claimed but untested** — no binary here. | high | Refuse-unless-bytes-match; solicit hashes; never claim tested. |
| 4 | **Ultrawide map stretch** (1.79× at 21:9, 2.67× at 32:9). Correct but ugly. | medium | Measure at 3440×1440 in Tier A, *then* decide. Do not decide from the algebra. |
| 5 | AV heuristics: PE section growth + frozen Python binary. | medium | `--onedir`, publish hashes, explain `pe_space` in the README. |
| 6 | Latent banker's-rounding bug at exact-half resolutions (§2.4). | low | `floor(x+0.5)`. |
| 7 | `lea ebx,[esp-0x400]` borrows below ESP; Win32 x86 has no red zone. | low but real | Recorded hazard. Shipping to strangers widens the sample; `sub esp, N` is strictly safer and cheap. |
| 8 | K1CP note interaction unquantified. | low | The `finalize` re-derivation test (§4). |

Risks 2, 5 and 10 of the 2026-08-29 draft (interface bucket, letterbox, GPL) are
**closed by the scope decision** in §0.

---

## 9. Recommended order of work

### 9.0 How phases are executed — user decision 2026-08-30

These are process rules, not implementation steps. They apply to every phase
below and to any future release plan in this project.

1. **Pause at every phase boundary.** When a phase completes, checkpoint it
   (`STATE.md` + the relevant `docs/` file + a commit), summarise what landed,
   then **ask whether to continue now or resume next session**. Do not roll
   from one phase into the next unprompted.
2. **Recommend a model before starting each phase, and say why.** State plainly
   whether the phase wants **Sonnet** (mechanical, well-specified work — file
   moves, installs, running an existing script, packaging) or **Opus**
   (byte-level reverse engineering, ambiguous evidence, judgement calls where a
   wrong conclusion would be recorded as CONFIRMED and poison later phases).
   Say it *before* the work starts, so the user can switch and save tokens.
   The user is on a token subscription — see the session-continuity rules in
   the project `CLAUDE.md`.
3. **Model guidance for the phases in this plan** (revise per phase as scope
   becomes clearer):
   - Phase 0 preserve — **Sonnet** (done; git and pip mechanics).
   - Phase 1 official-chain validation — **Opus**. This promotes §2.7 from
     INFERRED to CONFIRMED against risk #2, the highest open risk; it is
     byte-diff reading and conflict-vs-rounding judgement.
   - Phase 2 patcher — **Opus** for the pipeline and auto-detect design (§5.1),
     **Sonnet** acceptable for boilerplate once the design is fixed.
   - Phase 3 automated QA — **Sonnet** for wiring existing checks together;
     **Opus** if a check disagrees with the docs.
   - Phase 4 resolution testing — **Sonnet** to drive; the evidence is the
     user's own eyes in game.
   - Phase 5 compatibility testing — **Opus** for the overlap analysis
     (byte-range collisions, K1CP key survival), Sonnet to run the tests.
   - Phase 6 packaging — **Sonnet**.
   - Phase 7 icon scaling (1.1) — **Opus**; it is immediate-patching in the
     subsystem next door to the one that broke twice.

**Phase 0 — preserve (~30 min). DONE 2026-08-30.** `git init`; `.gitignore`
`backups/`, `downloads/`, `staging/`, `__pycache__`. Commit docs, tools,
`output/*.csv`, atlas ink. `pip install pytest pyinstaller`. Private GitHub
repo `github.com/Xerlok/kotor-resolution`; initial commit `42920cc`.

**Phase 1 — build and validate the real supported chain. DONE 2026-08-30.**
~~From a stock Editable Executable: official UniWS → official k1hrm (letterbox
yes) → our three layers. Full Tier A pass at 2560×1600 on *that* binary.~~
**§2.7 is CONFIRMED (§2.9): the chain reproduces the live exe byte-for-byte
(md5 `435108fd…`), so the existing in-game confirmation already covers it and no
fresh Tier A pass was required at 2560×1600.** Repro script:
`tools/verify_official_chain.py`. The one gap left is the letterbox-on
configuration (§2.9), deferred to Phase 4.

**Phase 2 — the patcher. DONE 2026-08-30.** `patcher/` — one entry point,
resolution auto-detect (§5.1), build fingerprint, 19 post-write checks, JSON
manifest, `Apply.bat`/`Revert.bat`. Acceptance test `patcher/selftest.py`
reproduces the in-game-confirmed exe byte for byte (md5 `435108fd…`) and covers
six refusal/revert cases. See §2.10 and CURRENT_STATE.md.

**Phase 3 — automated QA.** Per-resolution checks across all 49 sets; the
note-table end-to-end simulation (exists, wire it in); the K1CP key-survival
test. One command, one report.

**Phase 4 — resolution testing.** Enable DSR/VSR. Tier A manual, then Tier B
smoke. Results become the README's support matrix.

**Phase 5 — compatibility testing.** §4's matrix; K1CP and the Ultrawide
Letterbox Fix first.

**Phase 6 — package and release 1.0.** Freeze, hashes, GPLv3 licence file and
ndix UR credit, README with raw offsets and cave ranges (k1hrm precedent),
troubleshooting doc.

**Phase 7 — 1.1: marker icon scaling** (§6).

---

## 10. Deferred to a future release

- **`dinput8.dll` / ASI and packed-Steam-exe support** (§7).
- **Marker icon scaling** — 1.1 (§6).
- **The player/party double-rounding fix** (≤2 px; vanilla is imprecise too). The
  right fix is at the writer `0x5790C0`, in the subsystem that broke twice.
- **The Area Map frame line** — DXT1 art editing on an asset k1hrm owns.
- **HD map art** (KPM's `hud-minimap-map-size-fix-v1` is verified applicable).
- **Our own `generate_gui.py`** — blocked on open question 2, learning value only.
- **The HoloPatcher new-game-only data variant** (`tools/make_git_edit.py`).
- **Blue transition lines with no note** — needs the disqualified data-edit route
  ([F17](EXPERIMENTS_AND_FAILED_APPROACHES.md#f17)).
- **The 32:9 uniform-scale map model** — only if Phase 4 shows the stretch is
  unacceptable.

---

## 11. Open uncertainties

Recorded so they are not quietly promoted to CONFIRMED:

1. ~~**Our layer on the official UniWS + k1hrm chain** — INFERRED (§2.7). Phase 1.~~
   **RESOLVED 2026-08-30: CONFIRMED byte-for-byte** (§2.9). Replaced by a
   narrower one: **the letterbox-on configuration has never been run in game**
   (3 bytes at `0x355788`), while §4's install order recommends it.
2. **GOG and retail 4-CD patchability** — researched, no binary here.
3. **Byte-range overlap** with the Ultrawide Letterbox Fix.
4. **Marker materials: procedural or resampled textures?** (§6)
5. **Does K1CP move any map note?** (§4) — cheaply answerable, not yet answered.
6. Carried from [FUTURE_WORK](FUTURE_WORK.md): the widened bound check's effect on
   the generic HUD path, and the vanilla float twins `0x747748`/`0x7455D4`.
7. **Does "3440x1440 Enhanced HUD/UI and Menus" ship or edit `map.gui`?** (§4) —
   if it does, it collides with k1hrm's per-resolution GUI set rather than adding
   alongside it. Cheaply answerable by inspecting the mod's file list; not yet
   checked. Researched 2026-08-30 alongside the Flawless Widescreen finding
   (different mechanism, declared incompatible — not an open uncertainty).
