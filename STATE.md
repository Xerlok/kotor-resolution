# STATE — start here

**The knowledge base is [`docs/`](docs/README.md). Read
[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) first, then whichever of the
other nine documents your task touches.**

Before trusting any document, run:

    python tools/state.py

It reconstructs what is applied straight from the binary and the CSVs, so it is
correct even when the docs are stale.

## Active work (2026-09-01): shipping & QA

The project has moved from development into **shipping**. The plan is
[`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md) (plain-language version:
[`docs/RELEASE_PLAN_SIMPLE.md`](docs/RELEASE_PLAN_SIMPLE.md)).
**Approved by the user 2026-08-30. Phases 0-6 (§9) are DONE. The 1.0 release
is built and its acceptance test passes; nothing has been published.** The only
phase left in the plan is Phase 7 (1.1). Phases pause for the user's go-ahead at
each boundary and carry a Sonnet/Opus recommendation — see §9.0 of the plan.

### Distribution shape — decided 2026-08-30. Backup relocation + Python-free install DONE 2026-08-31

**Ship the multi-file archive that is already built; do NOT wrap it in an
installer exe.** Full record, including the arguments to stop re-litigating:
[`docs/DISTRIBUTION_DECISION.md`](docs/DISTRIBUTION_DECISION.md).

**Done 2026-08-31 (user go-ahead), no patch bytes changed —
`patcher/selftest.py` 9/9 to md5 `435108fd…`, `tools/verify_release.py` 33/33:**

1. **The player's backup no longer lives in the download.**
   `backup\swkotor.exe.original` + `installed.json` now go to
   `%LOCALAPPDATA%\K1AreaMapFixes\`. `manifest._home()` split into
   `visible_home()` (holds `last-run-log.txt`, found by walking up to
   `Install.bat`) and `_data_home()`. **A development checkout still uses
   `patcher/`** — the marker is `patcher/selftest.py`, which never ships — so
   `tools/state.py`, the docs, and **the user's live install's `Revert.bat`**
   are unaffected (verified: record still found in `patcher/`). An
   `installed.json` left in an older release folder also keeps working.
2. **Running from inside the zip is refused**, `detect.check_not_temp()` from
   `install.py`. In the patcher rather than in `Install.bat`, so it also covers
   double-clicking `Patcher\K1AreaMapFixes.exe`. Revert is deliberately not
   gated — that is the recovery route.
3. **Python is NOT required, and the README now says so.** Both frozen exes do
   a full apply → uninstall with `PATH` cut to `System32` and every `PYTHON*`
   var removed, and no shipped module contains `subprocess`/`os.system`/
   `os.popen`/`shutil.which` at all. Caveat: stripped environment, not a clean
   VM — see Q1 in the decision doc.
4. **`tools/verify_release.py` grew 12 checks** and **redirects
   `%LOCALAPPDATA%` into `staging/`** instead of mocking the path, so what the
   player gets is what is tested. The load-bearing one: **delete the release
   folder, re-extract it, and uninstall anyway.**

Docs rewritten for the new location: `README.txt` (no more "keep this folder";
names `%LOCALAPPDATA%\K1AreaMapFixes\backup` and the re-download route),
`TROUBLESHOOTING.txt` (two entries replaced — "it says to unzip first" and "I
deleted the mod folder", plus where `installed.json` is now and that both files
contain the player's game path), `TECHNICAL.txt`, `Uninstall.bat`'s no-Python
fallback message.

**Release rebuilt: 43 files, 12.0 MB, zip sha256
`17c209e985db909778e9b9e812d9b313948ceb051e29fb167013db401ad8bfbe`.** Version
still **1.0.0** — nothing was ever published, so there is nothing to supersede.

**Still open from that doc:** Q2's Steam-only legal/naming half — is a link to
a third-party unlock tool something to publish under our own name? (Q2's GOG
half is answered and shipped, see below.) Q3 — rework the "I couldn't find your
KOTOR folder / drag it onto Install.bat" prompt.

**New open question, raised 2026-09-01 during the clean-install test: is k1hrm
reliable enough to stay a required prerequisite?** Second independent defect
found in its shipped Windows path — see
[F26](docs/EXPERIMENTS_AND_FAILED_APPROACHES.md#f26) (`hires_patcher.bat` calls
`hires_patcher` by bare name, breaks under "Run as administrator"; F25 was the
`.exe`/`.pl` centring-constant mismatch). Consider whether to write our own
per-resolution GUI-layout patcher instead of depending on k1hrm for that half
(UniWS, the engine-level half, has never shown a defect here). Not decided —
needs weighing against reimplementing k1hrm's 49-resolution-set coverage.

### NEXT SESSION STARTS HERE — text/UX/tooling session, 2026-09-01. No patch bytes touched.

**Everything below is text, console-output, and dev-tooling work. `selftest.py`
reproduces md5 `435108fdb65bac2151ab694e7fb8e36a` throughout — nothing here
touched a patch offset.** GOG clean-install test (previous session) is closed;
see `docs/RELEASE_PLAN.md`/`REVERSE_ENGINEERING.md` for that record.

**1. GOG-vs-Steam corrections shipped**, closing the loop that test was meant to
surface: `README.txt`, `TROUBLESHOOTING.txt`, `TECHNICAL.txt`,
`COMPATIBILITY.txt`, and the `detect.check_build` refusal message all now split
Steam (needs the Editable Executable) from GOG (doesn't) instead of blaming
both. `docs/PROPOSED_MESSAGES.md` and Q2 in `docs/DISTRIBUTION_DECISION.md`
updated to match. Commit `6272551`.

**2. Install/Uninstall console output redesigned** (user-specified format):
labelled `Checking your game...` block, a `Patching...` checklist, boxed
`====` banners for every outcome (success/refusal/crash) via new
`patcher/k1amf/ui.py`. ASCII marks only (`+`, not a Unicode checkmark) plus a
defensive `sys.stdout.reconfigure` — a real checkmark can crash a frozen
console app depending on the player's codepage, not a risk worth it for a
double-clicked `.bat`. `Uninstall.bat` now prints `Uninstalling...` immediately
instead of going silent. The k1hrm-centring-defect explanation moved from
`out.say` to `out.detail` (still in `last-run-log.txt` / `--details`, just not
shown to a normal player by default). Commit `0366795`.

**3. Real bug found and fixed: backups were never deleted.**
`manifest.backup_exe()` correctly avoids clobbering a backup of a *different*
pre-patch exe (timestamps a new one instead) — but nothing ever deleted a
backup once `Uninstall.bat` had verified the restore byte-exact, so every
install/uninstall cycle across a resolution or exe change left another copy in
`%LOCALAPPDATA%\K1AreaMapFixes\backup\` forever. Confirmed 4 accumulated copies
(~16 MB) on the dev machine. `revert.py` now deletes the backup file and the
(now-empty) `backup\` directory right after a verified restore, wrapped in
`try/except OSError` so cleanup can never fail an otherwise-successful
uninstall. `installed.json.reverted` is kept as-is, on purpose (audit trail).
**Those 4 pre-fix orphaned files still sit in the real
`%LOCALAPPDATA%\K1AreaMapFixes\backup\` on this machine — user has not said
whether to delete them; ask before touching, don't assume.** Commit `0366795`.

**4. Minimap scoping research, done then partially corrected same day.**
`docs/RELEASE_PLAN.md` §10 got new findings from a read-only investigation
(commit `5da764f`) — but one of them was **wrong**: it claimed no GFF/`.gui`
writer exists in this project. **`tools/gff_writer.py` has existed since the
initial commit** and is already used by `tools/map_frame_fix.py` and
`selftest.py`. Corrected in commit `2bdb673` — found while fact-checking the
new public README, before the error could spread there too. The real blocker
for a bigger HUD minimap is still exe-side only: `0x688100`'s shared constants
with the Area Map draw, and an unconfirmed `0x68ABF8` operand. Still correctly
a 1.1+ item, not something to pull into 1.0.

**5. `README.md` added at the repo root** — GitHub had nothing to render on the
landing page. Written for a visitor (features, requirements, install,
compatibility, a technical overview, build/test commands). Deliberately no
link to the Editable Executable — named only, per Q2's still-open Steam-legal
question. Commit `7aacb8f`.

**`dist/` rebuilt and `tools/verify_release.py` re-run (ALL PASS) after each of
1–3 above** — the shipped release reflects all of it. Latest zip sha256
`a59401c1f9c2f0e61cc42a3ccaa1eee1b2fe4aac6b65b62b3224bf1d1c2bef37`, still 44
files / 12.0 MB / version 1.0.0.

**RESOLVED 2026-09-01 — the real Steam live install was manually tested end to
end by the user and confirmed good.** The chain reverted earlier that session
(vanilla + Editable Executable, `Override/` emptied) was finished by hand
(UniWS → k1hrm → this mod) and the user confirmed it all works. No longer an
open item; `tools/state.py` can still be run to see the current live state but
there is nothing outstanding to chase here. Worth keeping in mind for future
sessions only: copying a file into that Steam folder from an automated shell
hit real, reproducible interference (`ls`/`stat` saw the file, but every open
got `WinError 3` — resolved by having the user run the copy directly instead).

**RESOLVED 2026-09-01 — the 4 orphaned pre-fix backup files** in
`%LOCALAPPDATA%\K1AreaMapFixes\backup\` were deleted by the user. No longer an
open item.

**DECLINED 2026-09-01 — reporting the `hires_patcher.exe` F25 defect upstream
to ndix UR.** User decision: not doing this. Drop it from future open-item
lists.

**Public mod page copy written 2026-09-01: `docs/MOD_PAGE.md`.** The
DeadlyStream description, derived only from the shipped `patcher/README.txt`,
`COMPATIBILITY.txt` and `TECHNICAL.txt` — no new claims. Title used:
"K1 Area Map Fixes - High Resolution Area Map & Map Marker Fix" (keeps the
shipped name that the zip, folder and `%LOCALAPPDATA%\K1AreaMapFixes` all
carry, adds the searchable keywords). `docs/MOD_PAGE.html` is a local preview
of the same text, openable in a browser, with a copy-to-clipboard button; it is
a review aid, not a shipped file. Nexus copy not yet written.

**Q2 (README.md memory / DISTRIBUTION_DECISION.md) ANSWERED 2026-09-01 — link
the Editable Executable exe directly**, both in `README.txt` (already does,
`README.txt:25`) and in the DeadlyStream/Nexus page descriptions once written.
**Q3 CLOSED 2026-09-01 — the "couldn't find your KOTOR folder" prompt stays as
written, no polish pass.** Both closed in
`docs/DISTRIBUTION_DECISION.md`.

### Phase 6b — release polish, DONE 2026-08-30

A user-experience pass over the packaged release, driven by "pretend you have
never modded KOTOR". **The patch logic did not change: `selftest.py` still
reproduces md5 `435108fd…` and `verify_release.py` still passes.**

**Three real defects the packaging pass found:**

1. **The shipped source did not run.** `python source/install.py` died on
   `ModuleNotFoundError: backup_paths` — three of the four bundled `tools`
   modules import it and it was never copied in. Both README and
   TROUBLESHOOTING offer that command as the way to avoid running an unsigned
   exe, so we were shipping a promise that failed on first use. PyInstaller
   had found the module on its own, so the *frozen* build worked and hid it.
   `verify_release.py` now runs the shipped source and would catch it.
2. **`selftest.py` shipped but could not work** — it needs
   `staging/verify-chain/official/swkotor.exe`, a development fixture. Anyone
   curious got `missing fixture:` and would reasonably conclude the mod was
   broken. No longer shipped.
3. **Three docs pointed at `patcher\installed.json`**, which does not exist in
   the release — and that is the file bug reports are asked to attach.

**Layout: 8 files + 2 folders at top level → 3 files + 2 folders.**

    Install.bat  Uninstall.bat  README.txt  Patcher\  "More info"\

`Apply/Revert.bat` were renamed `Install/Uninstall.bat` (user decision; note
this breaks the community `Apply X.bat` convention deliberately, for people who
have never modded). `manifest._home()` anchors on `Install.bat` — **if the bat
is ever renamed again, that function must change with it.** Licence, hashes,
technical/compatibility notes and the Python source moved under `More info\`.

**Output rewritten for a non-technical player.** Default install output is
plain English with no hex, no "cave"/"hook"/"operand", no `Hellspawn Reborn`
line. **`--details` reproduces the old engineer output verbatim, and
`last-run-log.txt` is written next to `Install.bat` on every run regardless**,
so a bug report is a file to attach rather than a flag to re-run with.
Refusals lead with what to do, and the three "someone else edited this" gates
now share one message (`detect._MEDDLED`) instead of three variants. Full
rationale and before/after: [`PROPOSED_MESSAGES.md`](PROPOSED_MESSAGES.md) —
**`selftest.py` asserts on several of those strings.**

**README rewritten** for someone who has never modded: names all three
prerequisites with links (verified live 2026-08-30), and covers four things
that previously stopped a beginner dead and were documented nowhere —
SmartScreen's "Windows protected your PC", running the bat from *inside* the
zip (backup goes to a temp folder, uninstall later fails), **drag-and-drop of
the game folder onto `Install.bat`, which already worked and was never written
down**, and UniWS needing the **1024x768** interface, not 800x600.

**Privacy audit: clean.** All 44 files scanned — text, both frozen `.exe`s,
`base_library.zip` decompressed, every DLL/PYD, and the note table. No
username, machine name, real path, email or GitHub handle. Build-machine paths
do not survive freezing. The only absolute path is the invented
`D:\SteamLibrary\...` example. Note that `installed.json` and
`last-run-log.txt` *do* contain the player's own game path — TROUBLESHOOTING
now says so where it asks for them.

### Phase 6 — DONE 2026-08-30. There is a shippable release.

    python tools/build_release.py      # freeze + assemble + hash + zip
    python tools/verify_release.py     # acceptance test on the ARTIFACT

`dist/K1-Area-Map-Fixes-1.0.0/` and `.zip` — 12.0 MB, 43 files, version frozen
at **1.0.0**. `dist/` is gitignored: the artifact is regenerable, and the two
commands above are the record. **Nothing was published** — no upload, no GitHub
release, repo still private (user decision).

`tools/verify_release.py` runs the **shipped `.exe` files**, not the source,
end to end against a throwaway game folder: apply → md5
`435108fdb65bac2151ab694e7fb8e36a`, the in-game-confirmed exe; second apply
refused; revert byte-exact; install record lands beside `Apply.bat`. All pass.
`patcher/selftest.py` still 9/9 to the same md5.

**Freezing the patcher found two defects the source test could not.** Both are
the reason `verify_release.py` exists as a separate gate:

1. **PyInstaller collected keystone's `.py` files but not `keystone.dll`.**
   The match routine is assembled at install time, so keystone is a *runtime*
   dependency; without the DLL beside its own `__file__`, `keystone.py` falls
   through to a `distutils.sysconfig` fallback that Python 3.12 removed, and
   the frozen patcher died mid-run on `No module named 'distutils'`. Fixed by
   bundling the DLL into `keystone/`. PyInstaller hooks capstone, not keystone.
2. **The frozen build wrote the player's only exe backup into `_internal/`.**
   `manifest.HERE` came from `__file__`, which under PyInstaller resolves
   inside `_MEIPASS`. `manifest._home()` now prefers the folder holding
   `Apply.bat` when frozen. Burying someone's only backup in `_internal` also
   means a re-download takes it with them.

Also: PyKotor — and so numpy and Pillow — was being pulled in through
`note_table_patch.build()`'s lazy `map_calibration` import, a path the shipped
patcher never takes. Excluded: **40.3 MB → 12.0 MB**.

**Four decisions, all the user's, 2026-08-30:**

1. **KPM: warn, don't refuse.** `detect.conflicting_mods()` looks for the five
   files §4 lists and prints a named warning; KPM is a patch *manager*, so its
   presence does not prove KotorUniResPatch is on. Confirmed firing.
2. **The LAA byte at `0x926`: no code change, document it.** On inspection the
   question was near-moot — `install.py:57` reads the before-image at the start
   of the run and compares it to the read-back from that same run, so a third
   party's bytes are in both images and cancel. The 20/21 in §4 needs another
   patcher to run *between* our snapshot and our verify, which is exactly what
   the Phase 5 test did; **a player cannot reach it through `Apply.bat`.**
3. **Bigger minimap: not in 1.0.** Deferred, §10 updated.
4. **Package only, publish nothing.**

**Documentation corrections made while packaging.** The post-write check count
is **21**, not 20 — counted from `verify.py` (18 `ok()` calls, two of them in
three-iteration loops), which matches Phase 5's measured 21/21. Fixed in
`STATE.md`, `CURRENT_STATE.md` and `RELEASE_PLAN.md`. And §4's "byte ranges to
publish" listed **one** marker hook where there are **three** (`0x6946D3`,
`0x694A42`, `0x694AB1`); all four hook sites are now published, in
`patcher/TECHNICAL.txt`.

**What ships:** `README.txt`, `COMPATIBILITY.txt`, `TROUBLESHOOTING.txt`,
`TECHNICAL.txt`, `LICENSE` (verbatim GPLv3, from k1hrm's own copy),
`SHA256SUMS.txt`, `Apply.bat`, `Revert.bat`, `source/`, `K1AreaMapFixes/`.

**Still open before anything is published:** report the `hires_patcher.exe`
defect (F25) upstream to ndix UR, and decide the release channel.

### Phase 5 — DONE 2026-08-30

**The whole published stack was confirmed in game together**, 2560×1600, the
first time every layer has run at once:

    k1hrm (letterbox ON) -> K1CP v1.10.0 -> Ultrawide Letterbox Fix -> ours

| check | result |
|---|---|
| Area Map fills its box | PASS |
| HUD minimap alive | PASS |
| map notes correct in a K1CP-patched module (`danm13`, Sandral estate) | PASS |
| player arrow + party markers | PASS |
| **Ebon Hawk area map** — `ebo_m40ad`, where K1CP moves 6 of the 35 waypoints it moves game-wide | **PASS, untouched** — `k1cp_keytest`'s "none of them are map notes" now holds in game, not just on disk |

**The Ultrawide Letterbox Fix's own feature is NOT observable at 16:10.** The
user reports the first-cutscene bottom bar and subtitles correct *both before
and after* applying it — consistent with it being an ultrawide fix for a bug
16:10 never had. **We claim coexistence, not that their fix works**; proving the
latter needs the 21:9 hardware Phase 4 recorded as unavailable (Tier C).

**True Controller Support** stays INFERRED — process-level `dinput8.dll` ASI,
no static overlap, not worth hardware time.

### Phase 5 detail

Three §4 rows closed with **no downloads and no game run**:

1. **KPM / KotorUniResPatch — incompatible, and detectable.** No static overlap
   with our hooks, caves, `.rsrc` region or private floats; it hooks the same
   function (`CSWGuiMapHider::Draw`) at `0x69473A`+9, past our `0x6946D3` /
   `0x6946EF`, and allocates at runtime. The conflict is the shared constants
   `0x747748`/`0x7455D4` and the rect immediates — it rescales what we already
   scaled. On-disk tells: `KotorPatcher.dll`, `hooks.toml`, `manifest.toml`,
   `patch_config.toml`, `KPatchLauncher`. **Open Phase 6 decision: warn or
   refuse?**
2. **Flawless Widescreen — incompatible, undetectable.** Live-process Lua
   injection, nothing on disk. Stays INFERRED; never run here.
3. **3440×1440 Enhanced HUD — compatible with us**, mutually exclusive with
   k1hrm's own 3440×1440 set (it ships all 81 of those filenames plus its own
   pre-patched exe). Its `map.gui` differs in size from k1hrm's but its
   **`LBL_Map` box is identical** — (511, 354, 2365, 768) = `expected_map_extent(3440,1440)`
   — so `check_map_gui` passes on either.

**F25 now has a second, independent witness.** That mod's bundled
`swkotor.exe` (4,042,752 B) carries the defect: canvas constants −3440/−1440,
all four centring sites left vanilla 640/480 → `detect.centring_state() ==
"stale"`. A *published* mod ships users into exactly the state §5.1 repairs.

Then, after the user downloaded the three archives:

4. **K1 Ultrawide Letterbox Fix — compatible, but THE INSTALL ORDER FLIPS.**
   No byte overlap (one 71-byte region at file `0x22B74E` + the PE `CheckSum`;
   it only *reads* `0x355788`). But **its patcher gates on exact file size
   `EXPECT_LEN = 4042752`**, and we grow the exe to 4,050,944 — so
   **ours-then-theirs is refused**, with a message that misleadingly blames the
   game build. Theirs-then-ours works: their patch survives byte-intact and all
   20 of our checks pass. Its *revert* has the same gate, so uninstall mirrors
   it: our `Revert.bat` first. §4.1 has the evidence; §4's published order is
   updated.
5. **4 GB patch (LAA) — compatible in both orders. CONFIRMED with the real
   NTCore binary** (the user ran it against our confirmed build `435108fd…`;
   `staging/4gb-real/`). It changes **exactly 3 bytes**: Characteristics
   `0x010F`→`0x012F` at file `0x926`, CheckSum `0x003E73F7`→`0x003E2782` at
   `0x968`. Section table and the whole `K1MAPNTS` region are byte-identical.
   The Python emulation used earlier predicted **both values exactly**, so that
   test is retroactively validated. `verify.check` returns **20/21** on the
   result — the one flag is `first stray: 0x926`, the LAA bit itself, correctly
   reported rather than a fault. **Phase 6 question: whitelist that byte, or
   leave the honest flag and explain it in the README?**
   **no-CD patchers are dropped from the matrix** — sourcing one means a cracked
   exe, and this covers the same PE-header risk.

**Documentation defect found and fixed while doing it.** §4's "byte ranges to
publish" list was unlabelled **virtual addresses**. File offset is `VA −
0x400000` for the hooks, caves and private floats — but the reserved `.rsrc`
region's delta is **`0x492000`** (`0x86D000` VA = file `0x3DB000`), because it
lives in our *extended* section. The exe is only `0x3DD000` bytes, so the
obvious subtraction sends a third-party investigator past EOF. Both numbers are
now published per range.

6. **K1CP v1.10.0 — CONFIRMED COMPATIBLE.** (Note the version: 1.10.0 is
   current; §4 had assumed 1.11.) Installed into a throwaway copy via
   HoloPatcher's CLI — 2227 patches, 0 errors, 0 warnings — then measured:
   **0 map notes moved, 0 added, 0 removed; 250/250 of our corrections still
   match.** Coverage: 85 of 90 note-bearing modules read from K1CP's own
   `.mod`. The pass is proved non-blind by `tools/k1cp_verify.py`: of **4,064
   waypoints compared, K1CP moves 35** — and **none of the 35 is a map note**.
   Report: `output/k1cp_keytest.json`.

**New tool: `tools/k1cp_keytest.py`** (read-only, no game needed beyond a
throwaway copy). Two reasons it is not `note_corrections.py finalize`:
`finalize` has no `--game` flag and would overwrite the shipped
`output/note_corrections.csv`; and — the load-bearing one —
`map_calibration.iter_modules` reads **`modules/*.rim` only**, while
HoloPatcher/TSLPatcher mods install **`modules/*.mod`**, which the engine
prefers. Reading `.rim` against a modded install reports zero changes whatever
the mod did: a false pass. The new tool reads `.mod` first, mirroring engine
priority. Validated against a clean copy: 90 modules, 340 notes, 250/250
corrections matching, 0 moved.

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

**Process rule added by the user 2026-08-30: `git push` at the end of every
phase**, not just commit. §9.0 rule 1's checkpoint now means
checkpoint + commit + push.

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

**The live install was restored to its pre-test state 2026-08-30, byte-exactly,
after the Phase 5 combined test.** It is again 2560×1600 with k1hrm's letterbox
ON and only our mod on top: **md5 `08567b1614e58db8d15e294018269a96`,
4,050,944 bytes — byte-identical to `backups/pre-k1cp-20260830-195230/swkotor.exe`.**
K1CP is gone (`modules/` back to 234 files, 0 `.mod`; `Override/` back to 81),
the Ultrawide Letterbox Fix is reverted, `tools/state.py` shows all five of our
layers, and the game folder holds no backup of ours.

`python tools/build_test_install.py 2560x1600 --letterbox no --home patcher`
still puts the exact confirmed build `435108fd…` back if a clean baseline is
wanted (the live build is that plus k1hrm's 3 letterbox bytes).

**One trap that restoration exposed, worth knowing before Phase 6.** Reverting
the Ultrawide Letterbox Fix does **not** return the exe to its previous bytes:
their patcher **recomputes the PE checksum** on both apply and revert, while
UniWS, k1hrm and our patcher all leave the field alone. So their revert left a
*correct* checksum `0x003E6A8C` where the chain base had a stale
`0x003E73F7` — same size, different md5, everything else identical (`0x22B74E`
verified restored). Restoring the field at file `0x968` made the base
byte-exact again, after which our patcher reproduced `08567b16…` on the nose.

**Consequence for our own docs and for users:** an md5 published for "k1hrm
output" is only stable if nobody has run a checksum-fixing tool over it. Our
patcher must keep identifying builds by *content* — the canvas constants and the
`detect.py` fingerprint — never by whole-file hash. It already does; do not
"improve" it into a hash check in Phase 6.

**`tools/qa.py` re-run 2026-08-30 after the marker-icon work: OVERALL PASS,
49/49 resolutions**, 800×600 to 15360×8640, ~17 min. The note-table block passes
too (250 corrections, 340 keys, 0 shared, frozen table matches a fresh derive).
Report: `output/qa_report.json`. `patcher/selftest.py` passes 9/9.

**Phase 2 — done 2026-08-30. There is now a patcher a player can run:**

    python patcher/selftest.py     # the acceptance test — run this first

`patcher/install.py` (`Apply.bat`) applies all five layers in one pass, reads the
resolution out of the exe instead of asking, cross-checks `Override/map.gui`,
runs 21 post-write checks against a fresh read from disk, and writes a JSON
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
