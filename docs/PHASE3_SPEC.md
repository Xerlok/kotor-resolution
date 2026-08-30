# Phase 3 — automated QA: specification

Written 2026-08-30 (Opus) as the handoff for a **Sonnet** session. The design
calls below are already decided; do not re-litigate them. Escalate back to Opus
only if a check **disagrees with the docs** — that is a finding, not a bug in
the check, until proven otherwise.

Goal: **one command, one report.**

    python tools/qa.py            # runs everything, prints a summary, exits 0/1
    python tools/qa.py --json out/qa_report.json

## What it must cover

### A. Per-resolution checks across all 49 k1hrm sets (no game needed)

k1hrm 1.5 ships its sets as `downloads/k1hrm-1.5/<aspect>/gui.<W>x<H>/` —
5 aspect dirs, **49** resolution dirs total. Enumerate them from disk; do not
hardcode a list.

For each resolution, build a test binary and assert:

1. `Override/map.gui`'s `LBL_Map` extent equals `detect.expected_map_extent(w, h)`,
   within `detect.GUI_TOLERANCE` (1 px — 3 of the 49 sets differ from the formula
   by a rounding pixel; that is known and accepted, §2.2).
   Read the set's *own* `map.gui`, not the live install's.
2. Shared floats `0x747748` / `0x7455D4` still read **440.0 / 256.0** — i.e. we
   never wrote them in place. This is the regression that turned the HUD minimap
   black; it is the single most important assertion in the whole harness.
3. Operands at `0x6944A8` / `0x6944C4` point at `0x78CC00` / `0x78CC04` (the
   private float copies).
4. Every int16 write is in range.
5. The note table round-trips byte-identical.
6. **The stale-k1hrm input converges** (added 2026-08-30, Phase 4). k1hrm's four
   Area Map centring constants are rolled back to vanilla 640/480 — the exact
   6-byte difference between `hires_patcher.exe`'s output and
   `hires_patcher.pl`'s ([F25](EXPERIMENTS_AND_FAILED_APPROACHES.md#f25)) — and
   the whole pipeline must detect it and produce **byte-identical output** to the
   clean base. Note *why* this is not redundant with the battery below: the chain
   in the next section builds with the `.pl`, which writes those constants
   correctly, so the input a real Windows user actually gets from
   `hires_patcher.exe` never occurs here unless it is constructed deliberately.
   A whole class of prerequisite breakage is invisible to a harness that only
   ever feeds itself correct input.

Do not write these from scratch. `patcher/k1amf/verify.py:check(before, after,
width, height, table, code_va, table_va)` is the existing 20-check battery from
Phase 2 and already covers most of 2–4; call it per resolution and add whatever
it does not cover. `detect.expected_map_extent` and `detect.check_map_gui`
already exist for 1.

### How to build the test binary at each resolution — decided, do not redesign

Chain per resolution:

    backups/swkotor.exe.uniws-only-backup        (official UniWS artifact)
      -> official k1hrm at W x H  (downloads/k1hrm-1.5/hires_patcher.pl, perl is
                                   installed and on PATH; v5.42.3 confirmed)
      -> our layer via patcher/k1amf/steps.py:apply_all(data, w, h, table)

`tools/verify_official_chain.py` already takes `[WIDTH HEIGHT]` and does exactly
this chain — reuse its machinery rather than duplicating it.

**Known and accepted limitation, state it in the report:** the UniWS-only base
is a 2560x1600 artifact, so in every test binary the *UniWS* layer's own
resolution bytes stay at 2560x1600 while the k1hrm layer is at W x H. This does
not affect anything under test: our layer's only inputs are the resolution read
from k1hrm's canvas constants at `0xB6C7`/`0xB6DA` and the `map.gui` box. We are
QA-ing our layer, not UniWS. Do **not** try to fix this with
`tools/uniws_patch.py` — that tool only ever built the 1024-bucket test variant
and is not a faithful UniWS (§2.9).

Prefer the official `.pl` over our `hires_patch.patch()` port for the build. The
port is byte-identical (0 differing bytes, §2.9), so if 49 perl invocations turn
out to be slow, falling back to the port is legitimate — say which one the run
used in the report.

Work under `staging/`. **Never touch the real install.** Keep binaries in memory
where you can; 49 x 4 MB on disk is avoidable.

### B. Note-table end-to-end simulation

This already exists (the 2026-08-29 simulation: 250/250 corrections land on their
intended pixel, 0 unintended matches among the other notes). Phase 3's job is to
**wire it into `qa.py`**, not to rewrite it. Find it, call it, fold its numbers
into the report. If the current run disagrees with the recorded 250/250 + 0,
stop and escalate — that is a real finding.

### C. K1CP key-survival test — OUT OF SCOPE for Phase 3

Deferred to Phase 5 by user decision 2026-08-30. K1CP 1.11 is not in
`downloads/` and the test needs a download plus a throwaway HoloPatcher install.
Phase 3 stays fully offline and re-runnable with zero setup.

## Report

One table, one line per resolution, plus the note-table block and a final
PASS/FAIL. Non-zero exit on any failure so it can gate a release. Write the JSON
alongside so future runs can be diffed.

## Definition of done

- `python tools/qa.py` passes on all 49 sets from a clean checkout.
- The run is committed along with its JSON report.
- `STATE.md` and `docs/CURRENT_STATE.md` record that Phase 3 is done and what
  the harness covers.
- Per §9.0 rule 1: **pause and ask** before starting Phase 4.

## Rules that still apply

- Checkpoint per phase, not per step (project `CLAUDE.md`).
- Every backup goes through `tools/backup_paths.make_backup` — never next to the
  target, never inside the game folder.
- Numpy for the bulk byte comparisons; `verify_official_chain.py` already imports
  it as precedent.
