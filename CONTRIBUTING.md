# Contributing

## Where to start

Read [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) first, then whichever of
the other files in [`docs/`](docs/README.md) your change touches — that
directory is the consolidated knowledge base for this project.

Run `python tools/state.py` to reconstruct what is actually applied to the
binary straight from the exe and the CSVs; it is correct even when the docs
have gone stale.

## Binary patching rules

This project patches a shipped, closed-source game executable. The following
rules exist because getting them wrong corrupts a player's only copy of the
game binary.

- **No backup file ever goes inside the game folder.** Backups belong in
  `backups/` (or, for the shipped patcher, `%LOCALAPPDATA%\K1AreaMapFixes\`) —
  never next to the target as `file.backup`. Use
  `tools/backup_paths.make_backup(target, suffix)`, which places the backup
  correctly, verifies the copy, and refuses to silently overwrite a different
  existing backup.
- Always back up the target binary and record the byte offsets and original
  bytes before patching.
- After any patch, verify **both** the in-menu Area Map and the in-game HUD
  minimap before declaring success — a fix to one has broken the other before.
- If a patch regresses another subsystem, revert to the last known-good build
  and document the address and root cause in
  [`docs/EXPERIMENTS_AND_FAILED_APPROACHES.md`](docs/EXPERIMENTS_AND_FAILED_APPROACHES.md)
  rather than stacking a second fix on top of the first.
- Dry-run first (`plan`), then `apply`. Re-disassemble what is actually on disk
  afterward rather than trusting that the write did what was intended.

## Tests

```
python patcher/selftest.py     # acceptance test — patches the official-chain
                                # exe, requires it converge on the confirmed md5
python tools/qa.py             # sweeps all resolutions k1hrm supports
```

See [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) for the full test/build
command reference and what each one checks.
