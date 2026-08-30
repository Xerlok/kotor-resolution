# STATE — start here

**The knowledge base is [`docs/`](docs/README.md). Read
[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) first, then whichever of the
other nine documents your task touches.**

Before trusting any document, run:

    python tools/state.py

It reconstructs what is applied straight from the binary and the CSVs, so it is
correct even when the docs are stale.

## Active work (2026-08-30): shipping & QA

The project has moved from development into **shipping**. The plan is
[`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md) (plain-language version:
[`docs/RELEASE_PLAN_SIMPLE.md`](docs/RELEASE_PLAN_SIMPLE.md)).
**Approved by the user 2026-08-30. Phases 0-4 (§9) are done; Phase 5
(compatibility testing) is NEXT.** Phases pause for the user's go-ahead at each boundary
and carry a Sonnet/Opus recommendation — see §9.0 of the plan.

**Phase 3 — done 2026-08-30 (Sonnet). `tools/qa.py` passes: 49/49 resolutions,
note-table block clean.**

    python tools/qa.py --json output/qa_report.json

Per resolution (all 49 of k1hrm 1.5's sets, 800×600 to 15360×8640, discovered
from disk): builds the official-chain test binary (UniWS artifact → official
k1hrm at that resolution → our layer via `patcher/k1amf/steps.apply_all`), then
runs the same 20-check battery the shipped patcher runs
(`patcher/k1amf/verify.py:check`) plus the `Override/map.gui` `LBL_Map` box
check (`k1amf/detect.check_map_gui`), an int16-range assertion, and a
**stale-k1hrm convergence check** (added Phase 4 — see F25) against a fresh read
from disk: **23 checks per resolution**. Re-run 2026-08-30 after the F25 work:
**49/49 pass, 0 failures.** Separately,
`tools/note_corrections.build/validate` proves the position-key scheme
collision-free across **all 340** map notes in the game (not just the 250
corrected ones — 0 keys shared by more than one note), and
`tools/freeze_note_table` proves the shipped frozen table matches a fresh
re-derivation. Full spec: [`docs/PHASE3_SPEC.md`](docs/PHASE3_SPEC.md).
Report: `output/qa_report.json`.

The K1CP key-survival test was **moved to Phase 5** (user decision 2026-08-30)
so Phase 3 stayed fully offline — nothing here needed the game running or a
network fetch.

**Phase 4 (resolution testing) is DONE 2026-08-30.** Four resolutions confirmed
in game across three aspects (2560×1600, 1920×1080, 3840×2400, 1600×1200), the
letterbox question closed, 21:9 recorded as untestable on this hardware, and
`tools/qa.py` re-run to OVERALL PASS at 49/49. **Next: Phase 5, compatibility.**

**Phase 4's first pass found a real bug — in the prerequisite, not in us.
ROOT-CAUSED 2026-08-30:**
**k1hrm's shipped `hires_patcher.exe` leaves the Area Map's centring constants
at vanilla 640/480**, where `hires_patcher.pl` writes the target resolution.
The two outputs differ by exactly 6 bytes, all four map sites. The engine then
adds `((W-640)/2, (H-480)/2)` to the map art's origin — measured displacement
(642, 300) at 1920×1080, against (0, 0) on the confirmed-good 2560×1600 build.
**Our layer is correct; nothing about our patch needs changing.** Full evidence:
[F25](docs/EXPERIMENTS_AND_FAILED_APPROACHES.md#f25).

**Release consequence — HANDLED 2026-08-30 (user decision: detect and fix).**
k1hrm's own README and `.bat` tell Windows users to run the `.exe`, so the
*documented* prerequisite install breaks our headline feature and looks like our
bug. The patcher now reads those four sites and accepts exactly two states:
already correct (no-op), or exactly vanilla while the canvas constants prove
k1hrm ran at W×H (write W/H as its own manifest step, undone by Revert).
Anything else is refused. Design and rationale: `docs/RELEASE_PLAN.md` §5.1.

The proof it is a fix and not a guess: `patcher/selftest.py` rolls the four
sites back to vanilla and requires the result to converge on md5
`435108fdb65bac2151ab694e7fb8e36a` — the in-game-confirmed exe — and
`tools/qa.py` asserts the same convergence at all 49 resolutions.

**Also fixed 2026-08-30:** `patcher/selftest.py` read its `map.gui` fixture from
the *live* install, so it silently depended on whatever resolution this machine
was patched for and broke the moment Phase 4 rebuilt at 1920×1080. It now uses
k1hrm's shipped `gui.2560x1600/map.gui` (byte-identical, §2.9 point 4).

**Still open:** report the `hires_patcher.exe` defect upstream to ndix UR.

### Phase 4 results — final

| resolution | aspect | result |
|---|---|---|
| 2560×1600 | 16:10 | PASS — the reference build, confirmed before Phase 4 |
| 1920×1080 | 16:9 | PASS, all 5 items, after the F25 fix |
| 3840×2400 | 16:10 via DSR 2.25× | PASS, all 5 items — the largest scale factors run in game (kx=6, ky=5) |
| 1600×1200 | 4:3 | PASS, all 5 items — the control, the only aspect where kx == ky |
| 2560×1080 | 21:9 | **NOT TESTABLE on this hardware** — Tier C. A 16:10 panel enumerates no ultrawide mode, and windowed needs the client area to be *strictly* narrower than the desktop (the engine silently fell back to 800×600). Needs an NVIDIA custom resolution, which the user declined over its warranty warning. |

**Four resolutions, three aspects, every one green.** The remaining ~45 k1hrm
sets are "offline-verified, untested" (Tier C) — in those words, per §3.

Both of Phase 4's remaining items are now **done** — the 1600×1200 4:3 control
and the letterbox-on question, each confirmed in game 2026-08-30. See below.

### 1600×1200 — PASS, all 5 items, confirmed in game 2026-08-30

The 4:3 control is clear. It is the only aspect where **kx == ky**, so it is the
one case that would catch a regression anisotropic scaling masks. Marker scale
×1 there. Exe md5 `cd32a74b28e92004296c1a6184d379a2`.

### How it was deployed (2026-08-30)

    python tools/build_test_install.py 1600x1200 --letterbox yes

New dev tool, **not shipped**: builds the whole official chain (UniWS artifact →
official `hires_patcher.pl` at W×H → `patcher/install.py`) and deploys it to the
real install in one command — backing up the live exe, the 81 Override `.gui`
files and `swkotor.ini` into `backups/` first, then pointing the ini at W×H.
Record of what is live: `staging/testbuild/deployed.json`. Test builds write the
patcher's backup/manifest under `staging/testbuild/k1amf-home` (`--home patcher`
for a build you mean to keep). It reports, rather than enforces,
`backup_paths.assert_clean` — **UniWS's own `swkotore.undo1-4` /
`swkotorc.undom1-2` live in the game folder by its design** and must not be
deleted.

### Letterbox-on — CLOSED 2026-08-30, confirmed in game

Ran at 2560×1600, conversations normal. §2.9's last open item is answered.
Three findings, all load-bearing:

0. **What the option actually is.** One float at `0x355788`, the height factor
   for the black bars in the conversation cinematic view. Vanilla holds
   `0.428571` = `1/((4/3)·1.75)` — the 4:3 aspect baked in; k1hrm rewrites it to
   `1/(aspect·1.75)` (`hires_patcher.pl:179-180`). At 2560×1600 that is
   `0.357143`, a 17 % correction — visible only as slightly thinner bars, which
   is why it reads as "no visible change" at 16:10. Nothing to do with the map.

1. **It cannot be tested at 4:3 at all.** `hires_patcher.pl:181-184` forces
   `letterbox = 0` when `width/height == 4/3`. The 1600×1200 builds for `yes`
   and `no` are **byte-identical, 0 differing bytes** — the option is a no-op for
   every 4:3 user. So it was folded into the 2560×1600 restore build instead.
2. **Letterbox-on changes 3 bytes and nothing else.** The letterbox-**off**
   rebuild of the same chain reproduces the confirmed md5
   `435108fdb65bac2151ab694e7fb8e36a`, and the live letterbox-**on** build
   differs from it by exactly `0x355788`–`0x35578a`. That is outside every range
   our five layers touch, so **our patch is byte-identical under either
   answer** — which is what §2.9's open question was really asking. Confirmed in
   game the same day: conversations normal at 2560×1600 with it on.

`tools/qa.py:build_official_base` now takes `letterbox` as a parameter for this;
the sweep itself still runs the default `no`, matching the confirmed exe.

**Live right now: 2560×1600, letterbox ON, md5
`08567b1614e58db8d15e294018269a96`** — the daily-play build and the letterbox
test at once. Patcher backup and manifest are in the shipped `patcher/` location
for this one (`--home patcher`), so `Revert.bat` works on it normally.

### Marker icon scaling — SHIPPED IN 1.0 (2026-08-30)

Was deferred to 1.1; brought forward after 3840×2400 showed the markers too
small to use. **All 15 immediates — note, player-arrow and party markers —
scale together** by

    s = clamp(ceil(min(kx, ky) / (1600/480) - 0.25), 1, 8)

anchored so **2560×1600 → s=1 writes not one byte**, which is why
`patcher/selftest.py` still reproduces md5 `435108fd…`. 3840×2400 → 2, confirmed
in game. Across the 49 sets: 36 unchanged, 9 at 2×, 3 at 3×, 1 at 6×. Design and
the rejected alternatives: `docs/RELEASE_PLAN.md` §6.0.

Two facts found while doing it, both now in §6.0: the three marker materials are
`mm_barrow` (player), `lbl_mapcircle` (unselected note **and party — shared**)
and `whitetarget` (selected note); and the materials **resample cleanly**, which
§6 had recorded as UNKNOWN.

### The minimap — question answered, decision deferred

k1hrm **does** rescale the HUD (116 of `mipc16x12.gui`'s 120 controls). The
**four it deliberately leaves alone are the minimap group**, identical to vanilla
and across all 49 sets: `LBL_MAP` (512×512), `LBL_MAPVIEW` (**120×120** — the
visible size), `LBL_MAPBORDER`, `LBL_ARROW`. So the minimap is a fixed 120 px
box at every resolution. An earlier claim in §2.3 that "k1hrm does not scale the
HUD" was **wrong** and is corrected there. Whether to make it bigger is
**deferred to Phase 6 by user request** — see §10.

**⚠ The live install is 2560×1600 with k1hrm's letterbox ON** (md5
`08567b16…`), which is the confirmed build `435108fd…` plus those 3 letterbox
bytes — not the confirmed md5 itself. `python tools/build_test_install.py
2560x1600 --letterbox no --home patcher` puts the exact confirmed build back.

**`tools/qa.py` re-run 2026-08-30 after the marker-icon work: OVERALL PASS,
49/49 resolutions**, 800×600 to 15360×8640, ~17 min. The note-table block passes
too (250 corrections, 340 keys, 0 shared, frozen table matches a fresh derive).
Report: `output/qa_report.json`. `patcher/selftest.py` passes 9/9.

**Phase 2 — done 2026-08-30. There is now a patcher a player can run:**

    python patcher/selftest.py     # the acceptance test — run this first

`patcher/install.py` (`Apply.bat`) applies all five layers in one pass, reads the
resolution out of the exe instead of asking, cross-checks `Override/map.gui`,
runs 20 post-write checks against a fresh read from disk, and writes a JSON
manifest that `patcher/revert.py` (`Revert.bat`) undoes exactly. The self-test
patches the official-chain exe and requires md5 `435108fdb65bac2151ab694e7fb8e36a`
— **byte-for-byte the exe confirmed in game** — plus six refusal/revert cases.
Details in [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md); findings, including
why only **16** of the 17 map-scale sites are ever written, in §2.10 of the plan.

**Phase 1 — done 2026-08-30. The headline result of this project's QA so far:**
the officially-supported chain **rebuilds the live, in-game-confirmed exe
byte-for-byte** (md5 `435108fdb65bac2151ab694e7fb8e36a`). Re-runnable any time:

    python tools/verify_official_chain.py

So risk #2 is closed and §2.7 is CONFIRMED. Three supporting facts worth
knowing: our k1hrm port is **byte-identical** to official `hires_patcher.pl`
(0 differing bytes); the UniWS half was **always** the official GUI tool
(`staging/*.undo*` are its own undo records — `tools/uniws_patch.py` only ever
built the 1024-bucket test variant); and all **81** live `Override/*.gui` files
are byte-identical to k1hrm's shipped `gui.2560x1600` set. Details in
[`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md) §2.9.

**The one thing Phase 1 did NOT confirm:** the live exe was built with k1hrm's
dialogue letterbox **off**, but the published install order tells users to answer
**yes** — a 3-byte difference at `0x355788` that has never been run in game.
Deferred to Phase 4.

**Phase 0 — done 2026-08-30:** repo is now `git`-tracked (initial commit
`42920cc`, 573 files) and pushed to a **private** GitHub repo,
`github.com/Xerlok/kotor-resolution`. `.gitignore` excludes `backups/`,
`downloads/`, `staging/` (game binaries, third-party mod archives, disposable
test copies) — `source/` (`chitin.key`, `gui.bif`) and `reference/` are
tracked, per user decision. `pytest` and `pyinstaller` installed. Local git
identity is set to the GitHub noreply address for `Xerlok`, not a personal
email.

**Scope decided 2026-08-30: we ship only our own work.** The product is
**"K1 Area Map Fixes"** — one mod, one patcher, **GPLv3** — covering the Area Map
filling its box (plus the private-float split that keeps the HUD minimap alive),
the note/player/party marker fixes, and the 250 note-position corrections. Marker
icon scaling is 1.1.

**UniWS and k1hrm are now REQUIRED PREREQUISITES, not things we reimplement.**
`tools/uniws_patch.py` and `hires_patch.patch()` stay as dev tools for building
test binaries but are **not shipped**. The dialogue letterbox is k1hrm's own
patcher option (`LETTERBOX_SCALE`, defaults on) and is out of scope entirely.

Three things a fresh session should know:

1. **k1hrm 1.5 ships 49 resolution sets and our `mapscale` formula matches its
   `LBL_Map` box at every one of them** (46 exact, 3 off by 1 px of rounding, none
   a target). The minimap box is a fixed 512×512 in all 49. CONFIRMED 2026-08-30.
2. **We have never tested against the *official* UniWS + k1hrm chain** — every
   in-game confirmation to date is on a binary built by our own ports. That chain
   is now the only supported path, so proving it is Phase 1 and the top open risk.
3. **The patcher should read the resolution out of the exe, not ask for it.**
   k1hrm writes `-width`/`-height` over the vanilla `-640`/`-480` canvas constants
   (live exe reads −2560/−1600 at `0xB6C7`/`0xB6DA`), so those offsets both reveal
   the resolution and prove k1hrm was run.

## One-paragraph status (2026-08-29)

KOTOR 1 runs at 2560×1600 with correct GUI layout, working list-clicking, a
working HUD minimap, an Area Map that fills its box, and correct player/party
markers — all confirmed in game. On top of that, **250 map-note corrections are
live in the exe** (match routine `0x73C270`, table `0x86D010`, hook `0x6946EF`),
confirmed in game 2026-08-29 and **parked** by the user. Live exe md5
`435108fdb65bac2151ab694e7fb8e36a`, 4,050,944 bytes.

## The three things most likely to bite a fresh session

1. **Do not resize `LBL_Map`** in `Override/map.gui` (currently
   `380, 393, 1760, 853`). Growing it in any direction makes the engine smear the
   map texture's edge across the extra pixels. Tried twice, reverted twice.
2. **Do not rewrite the shared float constants** `0x747748` (440.0) /
   `0x7455D4` (256.0) in place — that is what turned the HUD minimap black.
   Redirect the *consumer's* operand to a private copy instead.
3. **`note_corrections.py finalize` is the gate.** Run it after touching any
   placement rule; it is the only thing that re-derives table keys from the real
   module files and re-checks round-trip, bounds and key uniqueness.

## Reverting

    backups/swkotor.exe.pre-notetable-backup.20260829-215022   # table only
    backups/swkotor.exe.pre-pe-extend-backup                   # table + PE extension
    python tools/vanilla_toggle.py vanilla                     # 100% vanilla, reversible

All backups live in `backups/` only — never in the game folder.

Full revert matrix, install manifest, and data sources:
[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).

## Archive

The original chronological notes (~6,800 lines) are in
[`docs/archive/`](docs/archive/README.md). **Do not read them unless the user
explicitly asks** — everything load-bearing is already consolidated in `docs/`.
