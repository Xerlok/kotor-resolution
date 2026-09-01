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
| **Map-note icon size** | 8 immediates in `CSWGuiMapHider` | **ours — SHIPPED IN 1.0** (§6.0); player arrow + party marker still deferred |

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
| ~~**Marker icon sizes still vanilla**~~ **PARTLY CLOSED 2026-08-30** | the two **note** icons now scale with the resolution (§6.0), confirmed in game at 3840×2400. The **player arrow** (`0x69405B` = `0x20`) and the party marker are still vanilla, by decision, and are the open half. |
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

### 2.3 The minimap is the ONE thing k1hrm deliberately does not scale

**Sharpened 2026-08-30** after the question "doesn't k1hrm change the minimap
size?" — the earlier answer here ("k1hrm does not scale the HUD") was **wrong**
and is corrected below.

**k1hrm does rescale the HUD.** Byte-comparing its `mipc*.gui` against the
vanilla copies extracted from `source/data/gui.bif`: all eight files differ, and
in `mipc16x12.gui` **116 of 120 controls** have rescaled extents (×1.6 / ×1.333
at 2560×1600, relative to the 1600×1200 bucket they are authored in) — e.g.
`LBL_MENUBG` (1348, 6, 245, 28) → (2157, 8, 392, 37).

**The 4 controls it leaves alone are exactly the minimap group**, and they are
byte-identical to vanilla *and* to each other across **all 49 sets**:

| control | extent, all 49 sets | what it is |
|---|---|---|
| `LBL_MAP` | (6, 6, **512, 512**) | the map quad — the 512 the tile math divides into |
| `LBL_MAPVIEW` | (6, 6, **120, 120**) | the **visible** minimap viewport |
| `LBL_MAPBORDER` | (−2, −3, 136, 137) | its frame |
| `LBL_ARROW` | (47, 49, 32, 32) | player arrow drawn on it |

So the on-screen minimap is a fixed **120×120** at every resolution: 10 % of a
1200-px-tall screen, 5 % of a 2400-px one. That is why it looks small at high
resolution while the rest of the HUD keeps up, and it is a deliberate choice by
ndix UR, not an oversight — almost certainly for the reason this project
rediscovered the hard way in [F6](EXPERIMENTS_AND_FAILED_APPROACHES.md#f6) /
[F8](EXPERIMENTS_AND_FAILED_APPROACHES.md#f8): the minimap's tile size comes from
the shared 440.0/256.0 constants against a fixed 512 map space, so growing its
box makes the engine smear or drop the quad rather than draw more map.

Previously known only for the four vanilla buckets. Confirms across the whole range why
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

### Results so far (Phase 4, 2026-08-30)

| resolution | aspect | tier | result |
|---|---|---|---|
| 2560×1600 | 16:10 | A | **PASS** — the reference build, confirmed in game before Phase 4 |
| 1920×1080 | 16:9 | A | **PASS**, all 5 checklist items, *after* [F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25). The first pass failed on item 1 and root-caused to k1hrm's `hires_patcher.exe`, not to us. Markers re-verified as registered with the art after the fix moved both. |
| 3840×2400 | 16:10 via DSR 2.25× | A | **PASS**, all 5 items — the largest scale factors run in game (kx=6, ky=5), and what brought marker icon scaling forward into 1.0 (§6.0) |
| 1600×1200 | 4:3 | B | **PASS**, all 5 items, 2026-08-30. The control: the only aspect where **kx == ky**, so the only one that catches a regression anisotropic scaling would mask. Marker scale ×1. |
| 2560×1080 | 21:9 | B | **NOT TESTABLE on this hardware** — Tier C. See the hardware correction below. |

Deploying a test build at any of the 49 sets is now one command,
`python tools/build_test_install.py WxH [--letterbox yes|no] [--home patcher]`
(dev tool, not shipped — see STATE.md for what it backs up and where it records
what is live).

### The letterbox gap — §2.9's question answered offline, 2026-08-30

**CLOSED**: run at 2560×1600 with the letterbox on, conversations normal.

What the option is: one float at `0x355788`, the height factor for the black
bars in the conversation cinematic view. Vanilla holds `0.428571` =
`1/((4/3)·1.75)`, the 4:3 aspect baked in; k1hrm rewrites it to
`1/(aspect·1.75)` (`hires_patcher.pl:179-180`), which at 16:10 is `0.357143` — a
17 % correction, so the visible difference is slightly thinner bars and nothing
else. It has no bearing on the Area Map. Three facts, found while trying to fold
it into the 4:3 control:

1. **It is a no-op at 4:3.** `hires_patcher.pl:181-184` sets `letterbox = 0`
   whenever `width/height == 4/3`, and the 1600×1200 builds for `yes` and `no`
   are byte-identical, 0 differing bytes. So a 4:3 build cannot test it however
   the question is answered, and no 4:3 user is ever affected by it.
2. **It is 3 bytes, outside everything we touch.** At 2560×1600 the
   letterbox-off chain rebuilds the in-game-confirmed exe
   (md5 `435108fd…`) and the letterbox-on build differs from it at exactly
   `0x355788`–`0x35578a`. **Our five layers are byte-identical under either
   answer**, so the published install order ("yes") cannot change our result —
   which is what §2.9 was actually asking. The remaining in-game check is
   cosmetic: does the dialogue bar look right, which is k1hrm's business.

Tested by running the 2560×1600 restore build with `--letterbox yes`, so normal
play doubles as the observation.

### Correction to the hardware assumption below — 2026-08-30

**"Anything larger needs Nvidia DSR" is wrong as a plan for Tier A.** DSR only
offers multiples of the panel's own resolution, so on a 2560×1600 (16:10) panel
it cannot produce 3440×1440 (21:9) or 3840×2160 (16:9) at all — those need
*custom resolutions*, not DSR.

It does not matter much for the *judgement*, because **the stretch is a property
of the aspect ratio, not of the size**: `kx/ky` is 1.792 at both 2560×1080 and
3440×1440, so the 21:9 call in Tier A can be made at 2560×1080.

**Second correction, same day — "fits the panel" is not the test.** Trying
2560×1080 proved it: the exe was correct at every layer (UniWS, k1hrm and ours
all read 2560×1080) and the game still ran at 1920×1080 with the whole 2560-wide
UI overflowing the right edge, because **a fullscreen mode must be *enumerated by
the display*, not merely be smaller than it**. A 16:10 panel exposes no ultrawide
modes. Nor does a bordered window help at 2560×1080: the window is ~8 px wider
than a 2560-wide screen.

The workable rig, then:

| aspect | how to test on a 2560×1600 panel |
|---|---|
| 16:10 | native (2560×1600); **3840×2400** via DSR 2.25× for the large case |
| 16:9 | 2560×1440 / 1920×1080 — standard modes, fullscreen just works |
| 4:3 | 2048×1536 / 1600×1200 — standard modes |
| 21:9 | **NVIDIA custom resolution required** (2560×1080) |
| 32:9 | custom resolution too (1920×540 is not a standard mode either) |

Diagnostic worth reusing: if the UI overflows but the patcher's checks all pass,
compare the *screenshot's* pixel size against `swkotor.ini` — a mismatch means
the engine fell back to another mode and the exe is not at fault.

**Windowed mode does not rescue 2560×1080 either — tried 2026-08-30.** With
`FullScreen=0` and `Width=2560` the engine fell back to **800×600** and did not
rewrite the ini. A window needs its client area *plus borders* to fit the
desktop, so 2560 px of client area cannot fit a 2560 px-wide desktop; this is a
hard refusal, not the few-pixel clip that was predicted. Windowed testing is
therefore only available for sets **strictly narrower** than the desktop.

**Consequence: 21:9 stays Tier C on this hardware** — offline-verified across all
49 sets, never run in game — unless someone tests it on a real ultrawide or
accepts NVIDIA's custom-resolution warranty warning. Recorded rather than
worked around, because §2.5 already establishes the 21:9 stretch is inherited
from k1hrm's box shape and is not ours to regress.

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
| **k1hrm 1.5** | exe + `.gui` | **REQUIRED** — our `mapscale` targets its box. **Its shipped `hires_patcher.exe` is defective** (leaves the Area Map centring constants vanilla, [F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25)); we detect and finish the job, §5.1 | CONFIRMED across 49 sets (§2.2); the `.exe`/`.pl` divergence CONFIRMED 2026-08-30 | precondition check + official-tool test |
| KOTOR Editable Executable | exe replacement | required on Steam | CONFIRMED | baseline |
| **K1CP 1.10.0** | data (HoloPatcher) | if it moves a note, our key stops matching → their fix wins | **CONFIRMED COMPATIBLE 2026-08-30 (Phase 5)** — it moves **35 waypoints, 0 of them map notes**; all **250/250** of our corrections still match. Note the version: 1.10.0 is current, not the 1.11 this plan assumed | `tools/k1cp_keytest.py`, below |
| **K1 Ultrawide Letterbox Fix** | exe patcher | complementary (§2.8) — **but it must be installed BEFORE us, not after**, reversing the order both projects publish. See §4.1 | **CONFIRMED 2026-08-30 (Phase 5)** — no byte overlap: one 71-byte region at file offset `0x22B74E` plus the PE `CheckSum` field. It only *reads* `0x355788`, never writes it | both orders tested offline; theirs-then-ours passes all 21 of our checks, ours-then-theirs is refused |
| True Controller Support | `dinput8.dll` ASI | process-level, no static overlap | INFERRED | launch + play |
| **KPM / KotorUniResPatch** | runtime DLL | **alternative, not addition — double-scales** | **RESOLVED 2026-08-30 (Phase 5)** — no static overlap with our hooks/caves/`.rsrc`/private floats; it hooks the same function at `0x69473A`+9, past our `0x6946D3`/`0x6946EF`, and allocates its own code via `VirtualAlloc`. The conflict is the **shared constants** `0x747748`/`0x7455D4` and the rect immediates: it re-scales what we already scaled, by `scale = max(1,(h+300)/600)` | declare incompatible; **detectable on disk** — `KotorPatcher.dll`, `hooks.toml`, `manifest.toml`, `patch_config.toml`, `KPatchLauncher` (+ a `binkw32.dll` proxy on Wine/Proton only) |
| **Flawless Widescreen** | runtime memory injection (Lua plugin, live process) | **different mechanism from our whole stack — nothing on disk to detect or gate against** | **RESOLVED 2026-08-30 (Phase 5) as far as it can be** — stays INFERRED; never run here. WSGF itself recommends UniWS+k1hrm for K1 and reserves FWS for K2/TSL | none possible; declare "not supported", same posture as KPM |
| **4 GB patch (LAA)** | PE header | **compatible in BOTH orders** — it changes two header fields and leaves the section table byte-identical, so our `.rsrc` extension is untouched | **CONFIRMED 2026-08-30 (Phase 5) with the real NTCore binary**, run by the user against our confirmed build `435108fd…`. It changes **exactly 3 bytes**: Characteristics `0x010F`→`0x012F` at file `0x926`, and CheckSum `0x003E73F7`→`0x003E2782` at `0x968`–`0x969`. Section table byte-identical; `K1MAPNTS` region byte-identical | LAA→ours: 21/21 checks pass. Ours→LAA: 20/21 — the one flag is `no byte outside this patcher's declared ranges was changed (first stray: 0x926)`, i.e. the LAA bit itself, correctly reported |
| no-CD patchers | exe | **dropped from the matrix 2026-08-30** — testing one means sourcing a cracked executable, and the 4 GB patch already exercises the same PE-header risk | not tested, INFERRED | document only |
| HD UI Menu Pack, Pretty Good! Icons, HD portraits, Main Menu Widescreen Fix | Override art | no shared ground | CONFIRMED | none |
| **KOTOR Widescreen Fade Fix** | Override art/texture | no shared ground (fade transition asset only) | INFERRED | none |
| **3440x1440 Enhanced HUD/UI and Menus** | Override `.gui` + **a pre-patched exe** | **REPLACEMENT for k1hrm's 3440×1440 set, not an addition** — ships all 81 of k1hrm's `gui.3440x1440` filenames plus `dialog.gui`, reuses `mipc16x12.gui` byte-identically, and bundles its own `swkotor.exe` | **RESOLVED 2026-08-30 (Phase 5).** Its `map.gui` differs from k1hrm's in file size (6988 vs 7347 B) but its **`LBL_Map` box is identical — (511, 354, 2365, 768), exactly `expected_map_extent(3440,1440)`**, so `check_map_gui` passes on either. Its bundled exe **carries the F25 defect** (canvas −3440/−1440, all four centring sites vanilla 640/480) → `centring_state() == "stale"`, which our patcher fixes | **compatible with us**, mutually exclusive with k1hrm's own 3440×1440 set. Ours applies on top of either |
| Larger Text Fonts | Override fonts | kills item stack counts | CONFIRMED, accepted | document only |

### The K1CP test — BUILT AND RUN 2026-08-30

`tools/k1cp_keytest.py <modded-game-dir> [--baseline <clean>] [--json out]`.
Read-only, offline, no game run. Report: `output/k1cp_keytest.json`.

**Result against K1CP v1.10.0** (installed into a throwaway copy via
HoloPatcher's CLI, `INSTALL.exe --game-dir … --install --console`: *"Successfully
completed 2227 total patches… 0 errors and 0 warnings"*):

| | |
|---|---|
| map notes moved | **0** |
| map notes added / removed | 0 / 0 |
| our 250 corrections still matching | **250** |
| coverage | 85 of 90 note-bearing modules, and 79 of the 83 holding our corrections, were read from K1CP's own `.mod` |

**Two traps this test had to avoid, both of which produce a silent false pass:**

1. **Resource priority.** `map_calibration.iter_modules` reads `modules/*.rim`
   only — correct for deriving the shipped table from a clean install, wrong
   here, because HoloPatcher installs `modules/*.mod` and the engine prefers
   them. Reading `.rim` against a modded install reports 0 changes no matter
   what the mod did. The tool reads `.mod` first. (Checked separately: K1CP
   installs **no** loose `.git`/`.are` into `Override/`, which would outrank
   both, and **no** container holds more than one GIT.)
2. **A zero that means "blind".** 0 moved is also what a broken reader returns.
   So `tools/k1cp_verify.py` compares **every** waypoint, note or not:
   **4,064 compared, 35 moved by K1CP, 0 of them map notes.** The reader
   demonstrably sees K1CP's edits; the notes genuinely do not move. That is what
   makes the pass real.

Do **not** substitute `note_corrections.py finalize` for this: it has no
`--game` flag and rewrites `output/note_corrections.csv` as a side effect, so
aiming it at a modded install would overwrite the shipped table.

Re-runs free on every future K1CP release.

### Published install order — REVISED 2026-08-30 (Phase 5)

```
Editable Executable (Steam only)
  -> swkotor.ini
  -> UniWS
  -> k1hrm            <- our prerequisite; answer YES to its letterbox prompt
  -> K1CP + content mods
  -> Ultrawide Letterbox Fix   <- MOVED: must come BEFORE us (§4.1)
  -> K1 Area Map Fixes  (ours) <- always the LAST exe patcher
```

Uninstall is the mirror: **`Revert.bat` (ours) first, then their `Revert Fix.bat`.**
Their revert carries the same size gate as their apply
(`patch_letterbox.py:190`), so it refuses while our +8 KB exe is in place.

### 4.1 Why the Ultrawide Letterbox Fix must go before us — CONFIRMED 2026-08-30

Both projects tell the user to install last. Only one of us can be, and the
constraint is asymmetric, so it is not a matter of preference:

- **Their patcher gates on exact file size**: `EXPECT_LEN = 4042752`
  (`patch_letterbox.py:50`, enforced at `:154` for apply and `:190` for revert).
- **We grow the exe by 8 KB** to host the note table — 4,042,752 → 4,050,944.

Both orders were built and tested offline at 2560×1600:

| order | result |
|---|---|
| **theirs → ours** | **works.** Their 71-byte patch at `0x22B74E` survives our layer byte-intact, and all 21 of our post-write checks pass |
| ours → theirs | **refused**, no changes written: `REFUSING: … is 4050944 bytes, expected 4042752. This patch targets the Steam/GOG English build.` — the size gate at `patch_letterbox.py:154-157`, which fires before their backup step |

Note their refusal message blames the *build*, not the size collision, so a user
who installs in the published order will conclude they have the wrong game
version. That is a support burden we can pre-empt in the README.

**What we confirmed in game, and what we did not.** The full stack ran at
2560×1600 (below). Their *own* feature was **not observable on this hardware**:
the user reports the first-cutscene bottom bar and subtitles correct both before
and after their patch. That is consistent — it is an **ultrawide** fix, and
16:10 never had the bug. So we claim **coexistence, confirmed**; we do not claim
their fix works, which needs the 21:9 hardware Phase 4 already recorded as
unavailable (Tier C).

**Their backup lands inside the game folder** (`swkotor.exe.bak-<timestamp>`,
`patch_letterbox.py:146-149`), which our own rule forbids for *our* files. Like
UniWS's `swkotore.undo1-4`, it is theirs by design: report it, never delete it.

### Byte ranges to publish

So a collision is diagnosable by someone who is not us. **These are virtual
addresses.** For most of them the file offset is `VA − 0x400000`, but the
reserved region is in our *extended* `.rsrc`, whose delta is `0x492000` — so
publish both numbers for it rather than letting a reader assume:

| what | VA | file offset |
|---|---|---|
| map-note marker hook | `0x6946D3` +5 | `0x2946D3` |
| party marker hook | `0x694A42` +5 | `0x294A42` |
| player marker hook | `0x694AB1` +5 | `0x294AB1` |
| note-table hook | `0x6946EF` +5 | `0x2946EF` |
| caves | `0x73C1D0`–`0x73C2A9` | `0x33C1D0`–`0x33C2A9` |
| private floats | `0x78CC00`–`0x78CC0F` | `0x38CC00`–`0x38CC0F` |
| reserved region (8 KB, magic `K1MAPNTS`) | `0x86D000` | **`0x3DB000`** |

**Corrected in Phase 6:** this table listed one marker hook where there are
three. All four hook sites are now published, generated from the same
`hires_patch` constants the patcher writes, in `patcher/TECHNICAL.txt`.

Verified against the live exe 2026-08-30: the magic occurs exactly once, at file
offset `0x3DB000`; the exe is `0x3DD000` bytes, so `0x86D000` is not a file
offset at all. `detect.py` separately uses **file** offsets for k1hrm's canvas
and F25 centring sites (`0xB6C7`, `0x2928B3`, …) — do not mix the two
conventions in one list without labelling them.

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

**A third check, added 2026-08-30 (Phase 4): finish k1hrm's job when its own
patcher didn't.** `hires_patcher.exe` — which k1hrm's `.bat` and README both
point Windows users at — leaves four Area Map centring constants at vanilla
640/480, where `hires_patcher.pl` writes the target resolution. The map art is
then drawn `((W-640)/2, (H-480)/2)` off its box. Full evidence:
[F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25).

The patcher now reads `0x2928B3`/`0x292959` and `0x2928C3`/`0x29296B` and
accepts exactly two states — already correct (do nothing), or exactly vanilla
*while the canvas constants already prove k1hrm ran at W×H* (write W/H, as its
own manifest step, undone by `Revert.bat`). Anything else is refused as an
edited build rather than guessed at.

**We fix rather than refuse** because the only honest alternative to offer the
player is "install Perl on Windows, or hex-edit four offsets k1hrm never
documented" — its README's manual technique misses them too. The decisive
evidence that this is a fix and not a guess: `patcher/selftest.py` rolls those
four sites back to vanilla on the official-chain base and requires the result to
converge on md5 `435108fd…`, **the in-game-confirmed exe**; `tools/qa.py` makes
the same convergence assertion at all 49 resolutions.

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

## 6. Map-note / icon scaling — **NOTE icons SHIPPED IN 1.0 (2026-08-30)**; player/party still open

### 6.0 What actually happened, 2026-08-30 (Phase 4)

Testing 3840×2400 in game, the user found the note markers too small to use and
asked for them doubled. Applied by hand to the live exe first, then wired into
the patcher once it looked right. **This section's design survived contact, with
three corrections recorded below.**

**The three marker materials are now catalogued** — they were listed as
uncatalogued sites here. Identified from the resrefs pushed in the constructor
at `0x693F60`:

| VA of push | resref | what it is | material size site |
|---|---|---|---|
| `0x69404C` | `mm_barrow` | player arrow | `0x69405B` (32) — **not scaled** |
| `0x6940CD` | `lbl_mapcircle` | unselected note | `0x6940DC` (16) |
| `0x694156` | `whitetarget` | selected note reticle | `0x69418F` (20) |

The note draw rects, both confirmed by disassembly: **selected** `0x69471F` size
20 with `0x694718`/`0x694724` offsets −10; **unselected** `0x694762` size 14 with
`0x694775`/`0x694778` offsets −7. The "uncatalogued −7 partner" this section
worried about is `0x694778`, and it is an `add edx, -7`, not a separate rect.

**Open question 4 is RESOLVED: the materials resample cleanly.** At s=2 and
3840×2400 the icons are crisp, not blurry, and the markers stayed on their rooms
— confirming [F9](EXPERIMENTS_AND_FAILED_APPROACHES.md#f9)'s half-size centring
holds at a scaled size. **CONFIRMED in game; it is the only icon size ever run.**

**The scale rule changed.** `clamp(round(min(kx, ky)), 1, 8)` as designed below
would give **3** at 2560×1600 — it rescales a baseline this project has played
for months and never complained about, and would break `selftest.py`'s
byte-for-byte reproduction of the confirmed exe. The shipped rule anchors on that
baseline instead:

    s = clamp(ceil(min(kx, ky) / (1600/480) - 0.25), 1, 8)

so **2560×1600 → 1 and writes not one byte**, and 3840×2400 → 2 as tested. The
`-0.25` steps up a quarter past each step rather than half — user decision
2026-08-30, taken over plain rounding (which leaves **3840×2160**, the commonest
4K target, at 1×, i.e. 26 % *smaller* than the baseline and near the size that
prompted this work) and over `ceil` (which pushes 2880×1800 to +78 % and reads
chunky). Across k1hrm's 49 sets: **36 unchanged, 9 at 2×, 3 at 3×, 1 at 6×**.

**Only the note icons ship.** The player arrow and party marker are untouched
pending a separate decision, so at a scaled resolution the player arrow is now
*smaller relative to the notes* than in vanilla. That is a deliberate, reversible
state, not an oversight.

Implementation: `hires_patch.NOTE_ICON_SITES` / `note_icon_scale()` /
`patch_note_icons()`, applied by `steps.apply_all` as its own manifest step, with
a `verify.check` assertion that each centring offset is exactly half its own draw
size — the property that keeps a marker on its room.

### 6.1 Original design notes (superseded where §6.0 says so)

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
| 9 | **We write four bytes that belong to k1hrm** (§5.1, [F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25)). Scope creep into a prerequisite, and `Revert.bat` puts the player back to a *broken* k1hrm rather than a good one. | low | Gated to the one measured starting state; refuses anything else; convergence on the confirmed exe asserted by `selftest.py` and at all 49 resolutions by `qa.py`. Say plainly in the README what we change and why, and report it upstream to ndix UR. |

Risks 2, 5 and 10 of the 2026-08-29 draft (interface bucket, letterbox, GPL) are
**closed by the scope decision** in §0.

---

## 9. Recommended order of work

### 9.0 How phases are executed — user decision 2026-08-30

These are process rules, not implementation steps. They apply to every phase
below and to any future release plan in this project.

1. **Pause at every phase boundary.** When a phase completes, checkpoint it
   (`STATE.md` + the relevant `docs/` file + a commit **and a `git push`** —
   user rule, 2026-08-30: the work is not checkpointed until it is off this
   machine), summarise what landed, then **ask whether to continue now or resume
   next session**. Do not roll from one phase into the next unprompted.
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
resolution auto-detect (§5.1), build fingerprint, 21 post-write checks, JSON
manifest, `Apply.bat`/`Revert.bat`. Acceptance test `patcher/selftest.py`
reproduces the in-game-confirmed exe byte for byte (md5 `435108fd…`) and covers
six refusal/revert cases. See §2.10 and CURRENT_STATE.md.

**Phase 3 — automated QA. DONE 2026-08-30.** `tools/qa.py` — **PASS, 49/49
k1hrm 1.5 resolutions**, plus the note-table position-key scheme proven
collision-free across all 340 map notes in the game and the frozen table proven
to match a fresh derivation. One command, one report:
`python tools/qa.py --json output/qa_report.json`. Full spec:
[`PHASE3_SPEC.md`](PHASE3_SPEC.md). **The K1CP key-survival test moved
to Phase 5 (user decision 2026-08-30)** — it needs a K1CP download and a
throwaway HoloPatcher install, and Phase 3 is worth more if it stays fully
offline and re-runnable with zero setup.

**Phase 4 — resolution testing. DONE 2026-08-30.** Four resolutions confirmed in
game across three aspects — 2560×1600, 1920×1080, 3840×2400 (DSR) and 1600×1200
as the 4:3 control — all 5 checklist items each. It found the F25 defect in
k1hrm's shipped `hires_patcher.exe` (root-caused, detected and fixed by our
patcher, §5.1) and brought marker icon scaling forward into 1.0 (§6.0). 21:9 and
32:9 are recorded as **not testable on this hardware** and stay Tier C. §2.9's
letterbox gap is closed. `tools/qa.py` re-run after the marker work: **OVERALL
PASS, 49/49**. The table above is the README's support matrix.

**Phase 5 — compatibility testing. DONE 2026-08-30.** Every row of §4's matrix
has a verdict, and the full published stack (k1hrm → K1CP → Ultrawide Letterbox
Fix → ours) was confirmed running together in game at 2560×1600 — Area Map,
HUD minimap, notes in a K1CP-patched module, markers, and the Ebon Hawk map
(the module where K1CP moves the most waypoints) all correct. See STATE.md.

Done, offline, no downloads needed:

- **KPM / KotorUniResPatch** — incompatible, failure mode named (double-scaling
  through `scale = max(1,(h+300)/600)`), and **detectable on disk**, so the
  patcher *can* warn. Whether it warns or refuses is a Phase 6 decision.
- **Flawless Widescreen** — incompatible, nothing on disk to gate against.
  Stays INFERRED; it is not run here.
- **3440×1440 Enhanced HUD** — compatible with us, mutually exclusive with
  k1hrm's own 3440×1440 set. It also gave [F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25)
  a second, independent witness: a **published** mod ships an exe in the
  fixable-stale centring state.

Blocked on downloads (nothing on disk — checked `downloads/`, `reference/`):
K1CP 1.11 + HoloPatcher, the Ultrawide Letterbox Fix, a 4 GB / no-CD patcher.

**Tooling note for the K1CP test.** Do **not** reuse `note_corrections.py
finalize` as-is: `build()` takes `game=`, but the `finalize` CLI has no `--game`
flag and writes `output/note_corrections.csv` as a side effect, so pointing it at
a K1CP install would overwrite the shipped 250-correction table. The test needs a
read-only wrapper (`tools/k1cp_keytest.py`) that calls `build(game=<throwaway>)`
and diffs the derived position keys against the frozen table.

**Phase 6 — package release 1.0. DONE 2026-08-30 (packaging only; nothing
published).** One command builds it, one command proves it:

    python tools/build_release.py      # freeze + assemble + hash + zip
    python tools/verify_release.py     # acceptance test on the ARTIFACT

`dist/K1-Area-Map-Fixes-1.0.0/` + `.zip`, 12.0 MB, 43 files. Version frozen at
**1.0.0**. `--onedir` per §5, source shipped alongside, `SHA256SUMS.txt` over
every file. Docs written: `README.txt` (rewritten: what is in the box, the
four in-game-confirmed resolutions, Steam/AV warnings, credits),
`COMPATIBILITY.txt` (install order + every §4 verdict in players' language),
`TROUBLESHOOTING.txt` (every refusal message, §5.2.5's list),
`TECHNICAL.txt` (every byte written, VA **and** file offset — the k1hrm
precedent, and §4's "byte ranges to publish" made complete). `LICENSE` is the
verbatim GPLv3.

**The four Phase 6 decisions, all user calls 2026-08-30:**

1. **KPM: warn, do not refuse.** KPM is a patch *manager*; `KotorPatcher.dll`
   on disk does not prove KotorUniResPatch is enabled, and the clash is
   cosmetic and reversible on both sides. `detect.conflicting_mods()` looks for
   the five files §4 lists and prints a named warning; `install.py` prints
   "no mod known to clash" otherwise. Confirmed firing.
2. **The LAA byte at `0x926`: leave the code alone, document it.** The question
   was near-moot on inspection: `install.py:57` reads the before-image at the
   start of the run and compares it to the read-back from that *same* run, so a
   third-party patcher's bytes appear in both images and cancel. The 20/21 in
   §4 is reachable only by running another patcher *between* our snapshot and
   our verify, which is what the Phase 5 test deliberately did — a player
   cannot hit it through `Apply.bat`. Whitelisting would have spent two bytes
   of stray-detection to fix a message nobody sees. `COMPATIBILITY.txt`
   explains the byte and tells users to LAA-patch *before* us, since
   `Revert.bat` restores a pre-LAA backup.
3. **The bigger minimap (§10): not in 1.0.** Stays deferred, unchanged reasons.
4. **Package only; publish nothing.** No DeadlyStream/Nexus upload, no GitHub
   release, repo stays private.

**Two defects found by testing the packaged artifact rather than the source** —
neither reachable from `patcher/selftest.py`, which is why
`tools/verify_release.py` exists:

- **PyInstaller collected keystone's `.py` files but not `keystone.dll`.**
  `note_table_patch.build_code` assembles the match routine at install time, so
  keystone is a *runtime* dependency. Without the DLL beside its own
  `__file__`, `keystone.py` falls through to a `distutils.sysconfig` fallback —
  removed from the stdlib in 3.12 — and the frozen patcher died mid-run with
  `No module named 'distutils'`. Fixed by bundling the DLL into `keystone/`.
  PyInstaller has a hook for capstone and none for keystone.
- **The frozen build wrote the player's only exe backup into `_internal/`.**
  `manifest.HERE` was derived from `__file__`, which under PyInstaller resolves
  inside `_MEIPASS`. `manifest._home()` now prefers the folder holding
  `Apply.bat` when frozen, falling back to the exe's own folder.

Also trimmed: PyKotor (and so numpy and Pillow) was being pulled in through
`note_table_patch.build()`'s lazy `map_calibration` import, a path the shipped
patcher never takes — 40 MB of a 63 MB build. Excluded; **40.3 MB → 12.0 MB**.

**Acceptance.** `tools/verify_release.py` runs the *shipped* `.exe` files end to
end against a throwaway game folder: apply → **md5
`435108fdb65bac2151ab694e7fb8e36a`**, the in-game-confirmed exe; refuses a
second apply; reverts to the exact pre-patch bytes; and asserts the install
record lands beside `Apply.bat`, not in `_internal`. **All pass.**
`patcher/selftest.py` still passes 9/9 to the same md5.

~~Also tidy the backup filenames.~~ **DONE 2026-08-30, and it needs no code
change.** `manifest.backup_exe` timestamping rather than overwriting is *correct*
for a player — a patcher must never destroy someone's backup. It only
accumulated here because development reinstalls dozens of times, and
`tools/build_test_install.py` now defaults to `--home staging`, so test builds no
longer write into `patcher/` at all. The four stale 4 MB copies were pruned
(20 MB → 3.9 MB), keeping only the one `patcher/installed.json` references;
`revert.py:38` resolves the backup from that field alone, never by filename.

**Phase 7 — 1.1: marker icon scaling** (§6).

---

## 10. Deferred to a future release

- **`dinput8.dll` / ASI and packed-Steam-exe support** (§7).
- ~~**Marker icon scaling** — 1.1 (§6).~~ **SHIPPED IN 1.0 2026-08-30** — notes,
  player arrow and party markers all scale together (§6.0).
- **A bigger HUD minimap — DECIDED 2026-08-30 at packaging: NOT in 1.0.** The
  user weighed it at the Phase 6 boundary as requested and deferred it, on the
  three reasons already recorded below. It is a 1.1 candidate alongside the
  remaining marker work; whether it lands as a feature of this mod or as a
  separate one is still open. The evidence gathered for the decision:
  §2.3 establishes the facts: the visible minimap is
  `LBL_MAPVIEW` at a fixed **120×120** at every resolution, and it is the one
  thing k1hrm deliberately declines to rescale while scaling 116 of the HUD's 120
  controls. At 3840×2400 that is 5 % of screen height and the user reports it as
  too small.
  **Why it is not a GUI-extent tweak:** the minimap's tile size comes from the
  shared 440.0/256.0 constants against a fixed 512 map space, so enlarging the box
  alone makes the engine smear or drop the quad — that is
  [F6](EXPERIMENTS_AND_FAILED_APPROACHES.md#f6)/[F8](EXPERIMENTS_AND_FAILED_APPROACHES.md#f8),
  and ndix UR evidently hit the same wall.
  **Why it now looks tractable:** we already solved this exact shape of problem
  for the Area Map — private scaled float copies plus a redirect of only the
  *consumer's* operands (`BIGMAP_FLOAT_OPERANDS`). The minimap's draw is a
  separate function at `0x688100` with its own `fdivr [0x747748]` at `0x688153`,
  so the same technique should apply to it independently.
  **Why it is not in 1.0:** it is new work in the subsystem with the worst track
  record in this project, it would also need `LBL_MAPVIEW`/`LBL_MAPBORDER`/
  `LBL_ARROW` moved in a file **k1hrm owns**, and 1.0's scope is deliberately
  "our own work only" (§0). Decide at packaging time whether it is a 1.1 feature
  or a separate mod; do not let it delay 1.0.
  **Scoping research done 2026-09-01 (read-only, no files touched) — confirms
  it's real work, still correctly kept out of 1.0:**
  - **CORRECTION, same day: the "no GFF writer" claim below was wrong.**
    `tools/gff_writer.py` (`dumps()`) has existed since the initial commit and
    is a real, exercised writer — `tools/map_frame_fix.py` uses it to rewrite
    `map.gui`'s `LBL_Map` extent in place on a live install, and
    `patcher/selftest.py` uses it to build a mismatched-`.gui` test fixture.
    `detect.check_map_gui` only *reads* `map.gui` because nothing has needed to
    *write* one in the shipped patcher yet, not because the capability is
    missing. So a `mipc16x12.gui` rect edit is not blocked on new GFF-writing
    work or a PyKotor size tradeoff — `gff.load` + `gff_writer.dumps` already
    do it. The real open questions are the exe-side ones below (§0x688100's own
    pixel bounds, isolating its operand from the Area Map's).
  - **`0x688100` also reads `0x68ABF8`, a real texture-size value**, not just
    the shared `0x747748`/`0x7455D4` pair — one more operand to account for in
    the redirect, and one more thing to confirm is minimap-only before touching
    it (same "verify by reference, not proximity" discipline F7 already taught
    the hard way).
  - **Two things still unconfirmed and must be answered (by disassembly, then
    an in-game test) before writing any patch code:** (1) whether `0x688100`
    has its own hardcoded pixel-loop bounds independent of the GUI `EXTENT` —
    if so a GUI-only resize can't work regardless of the exe redirect; (2)
    whether the goal is "same map content, rendered bigger" (likely a pure
    scale, closer to the marker-icon precedent) vs. "show more map area" (needs
    the 440/256 tile math itself to change — materially harder, and the one
    F6/F8 actually broke on).
  - Net: the marker-icon technique transfers in *shape*, not automatically in
    *safety* — confirms this stays a 1.1+ item with real pre-work, not a
    first-release candidate. **User confirmed 2026-09-01: not in the first
    release.**
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
4. ~~**Marker materials: procedural or resampled textures?** (§6)~~
   **RESOLVED 2026-08-30: they resample cleanly** — CONFIRMED in game at
   3840×2400, s=2, icons crisp and still registered on their rooms (§6.0).
5. **Does K1CP move any map note?** (§4) — cheaply answerable, not yet answered.
6. Carried from [FUTURE_WORK](FUTURE_WORK.md): the widened bound check's effect on
   the generic HUD path, and the vanilla float twins `0x747748`/`0x7455D4`.
7. ~~**Does "3440x1440 Enhanced HUD/UI and Menus" ship or edit `map.gui`?**~~
   **RESOLVED 2026-08-30 by inspecting `downloads/enhanced-hud-3440x1440/`.**
   **Yes** — it ships **82 `.gui` files**, including `map.gui` and all nine
   `mipc*.gui`. But its boxes are the *same* as k1hrm's: `map.gui` `LBL_Map` is
   `(511, 354, 2365, 768)`, byte-for-byte k1hrm's own `21-by-9/gui.3440x1440`
   value, and `mipc16x12.gui` `LBL_MAP` is `(6, 6, 512, 512)`, the same fixed
   minimap box as every one of the 49 sets (§2.3). So it is a **k1hrm-set
   replacement for one resolution, not an addition** — treat it that way in §4 —
   and it does **not** enlarge the HUD or minimap. Our `mapscale` formula and
   the `check_map_gui` gate agree with it at 3440×1440, so a user running it
   would pass our precondition check. Researched 2026-08-30 alongside the Flawless Widescreen finding
   (different mechanism, declared incompatible — not an open uncertainty).
