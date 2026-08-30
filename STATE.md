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
**Approved by the user 2026-08-30. Phases 0, 1 and 2 (§9) are done; Phase 3
(automated QA) is next.** Phases pause for the user's go-ahead at each boundary
and carry a Sonnet/Opus recommendation — see §9.0 of the plan.

**Phase 2 — done 2026-08-30. There is now a patcher a player can run:**

    python patcher/selftest.py     # the acceptance test — run this first

`patcher/install.py` (`Apply.bat`) applies all five layers in one pass, reads the
resolution out of the exe instead of asking, cross-checks `Override/map.gui`,
runs 19 post-write checks against a fresh read from disk, and writes a JSON
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
