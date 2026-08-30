## Session continuity — assume the session can end at ANY moment
The user is on a token subscription and can hit a limit without warning, so work
must be crash-safe at all times rather than tidied up at the end.

- **Start here:** read `STATE.md` (short) and run `python tools/state.py`, which
  reconstructs what is applied from the binary and CSVs. Then read
  `docs/CURRENT_STATE.md` and whichever of the other `docs/` files your task
  touches — that directory is the consolidated knowledge base (2026-08-29).
- **Do NOT read `docs/archive/` on your own.** It holds the original ~6,800-line
  chronological notes. Everything load-bearing is already in `docs/`. Read the
  archive only if the user explicitly asks for it.
- **Checkpoint per phase, not per step** (relaxed 2026-08-28 to cut token cost).
  Update the relevant `docs/` file and `STATE.md` when a phase completes, not
  after every step inside it. Keep intermediate findings in the conversation.
  New findings go into the topic file they belong to (`REVERSE_ENGINEERING.md`,
  `EXPERIMENTS_AND_FAILED_APPROACHES.md`, …), not into a new chronological log.
  Checkpoint immediately, mid-phase, only when one of these is true:
  - the game binary or any file in the real install was changed;
  - a finding cost real effort to obtain and could not be re-derived cheaply
    (a live debugger capture, an in-game observation, a user decision);
  - the user says "checkpoint";
  - the phase is about to run long or you are about to hand off.

  Everything else waits for the phase boundary. A finding that exists only in the
  conversation is still lost work if the session dies — so when in doubt about the
  two rules above, write it down.
- **Persist decisions as data, not prose.** Reviewer verdicts go in
  `output/note_decisions.csv` (with reasons); anything derived must be
  regenerable by a documented command, so a lost session costs minutes.
- **Never leave the binary in an unknown state.** Patchers must back up first,
  verify the readback, and refuse to run twice. If interrupted mid-change, the
  backup plus `tools/state.py` must be enough to tell what happened.
- When the user says "checkpoint", immediately flush state to disk before doing
  anything else.

## Binary patching rules (KOTOR mod work)
- **No backup file ever goes inside the game folder.** Backups live in
  `<project>/backups/` and nowhere else — the install must stay clean so that
  "what is deployed" is never ambiguous. Never write `target + ".backup"` next to
  the target; call `tools/backup_paths.make_backup(target, suffix)`, which puts it
  in `backups/`, verifies the copy, and refuses to overwrite a different existing
  backup (it timestamps instead). `backup_paths.assert_clean(game_dir)` checks the
  rule. This applies to anything transient too — stashed `Override/` files, test
  copies, saves.
- Always back up the target binary and record the byte offsets + original bytes before patching.
- After any patch, verify BOTH the in-menu Area Map and the in-game HUD minimap before declaring success.
- If a patch regresses another subsystem, revert to the last known-good build and document the address/root cause in `docs/EXPERIMENTS_AND_FAILED_APPROACHES.md` rather than stacking fixes.
- Dry-run first (`plan`), then `apply`. Re-disassemble what is on disk rather than trusting the write.
