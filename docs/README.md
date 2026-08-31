# KOTOR 1 Resolution & Map-Note Mod — project knowledge base

Consolidated 2026-08-29 from ~6,800 lines of chronological session notes. This
directory is the **long-term technical memory** of the project. It is written so
a session months from now can resume without rediscovering anything.

## Read in this order

| # | File | What it answers |
|---|---|---|
| 1 | [CURRENT_STATE.md](CURRENT_STATE.md) | What is installed right now, what works, what must not be touched |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | How KOTOR's map/GUI systems actually work |
| 3 | [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) | Every address, offset, constant and structure we know |
| 4 | [FIX_IMPLEMENTATION.md](FIX_IMPLEMENTATION.md) | Exactly what we changed and why it works |
| 5 | [MAP_NOTE_PIPELINE.md](MAP_NOTE_PIPELINE.md) | The data pipeline that produces the 250 corrections |
| 6 | [EXPERIMENTS_AND_FAILED_APPROACHES.md](EXPERIMENTS_AND_FAILED_APPROACHES.md) | What we tried, why it failed, what it taught |
| 7 | [DATA_FORMATS.md](DATA_FORMATS.md) | GFF/ERF/RIM/KEY-BIF/TPC/ARE/GIT/LYT/WOK/GUI |
| 8 | [TOOLS_AND_METHODOLOGY.md](TOOLS_AND_METHODOLOGY.md) | Tools, techniques, and the traps in each |
| 9 | [SHIPPING.md](SHIPPING.md) | How to package and distribute this to the community |
| 10 | [FUTURE_WORK.md](FUTURE_WORK.md) | Open questions, known limits, next steps |
| 11 | [RELEASE_PLAN.md](RELEASE_PLAN.md) | **The 2026-08-30 shipping/QA plan** — test matrices, install design, risks, order of work. Awaiting user approval |
| 12 | [RELEASE_PLAN_SIMPLE.md](RELEASE_PLAN_SIMPLE.md) | The same plan in plain language, no addresses |
| 13 | [DISTRIBUTION_DECISION.md](DISTRIBUTION_DECISION.md) | Installer-vs-archive decision (archive wins) + 3 open questions for next session |

`archive/` holds the original chronological notes. **Do not read the archive
unless the user explicitly asks for it** — everything load-bearing has been
consolidated here. See [archive/README.md](archive/README.md).

## Evidence labels used throughout

- **CONFIRMED** — established by code inspection, disassembly, debugging, an
  in-game observation, or a measurement that was actually run.
- **INFERRED** — our best explanation of the evidence, not directly verified.
- **UNKNOWN** — genuinely open.

These labels are not decoration. Several times in this project an INFERRED claim
was later disproven (see `EXPERIMENTS_AND_FAILED_APPROACHES.md`), so promoting
one to CONFIRMED without new evidence is a real error.

## What this project is

A **learning project in binary formats and reverse engineering**, whose practical
goal is running KOTOR 1 correctly at **2560×1600** (the target machine's native
resolution), using tooling we wrote rather than relying on pre-made presets.

It grew three strands:

1. **Resolution / GUI scaling** — get the engine to accept 2560×1600 and lay the
   2D UI out correctly. *Done, confirmed in game.*
2. **Area Map correctness** — the map fills its box, the HUD minimap renders,
   and player/party/note markers land in the right place. *Done, confirmed.*
3. **Map-note placement** — BioWare's own authored note positions are wrong
   across most of the game. We correct 250 of the 340 notes from an exe-side
   lookup table that touches no game data. *Done, confirmed in game 2026-08-29,
   parked by the user.*

## The single most useful property of the design

**Map-pixel space (0..440 × 0..256) is resolution independent.** The engine maps
world → map pixel → screen, and only the last step depends on resolution. The
correction table stores **world coordinates**, which sit upstream of the whole
chain. So one table is correct at every resolution, for free, forever. This is
why the note fix needs no per-resolution retuning and why it should be preserved
in any future redesign. CONFIRMED (algebra + in-game at 2560×1600).

## Ground rules that came from real incidents

1. **Look at the rendered picture before trusting any placement heuristic.**
   Every placement bug this project found was found that way, not by reasoning.
2. **Any float written to a file and later compared for bit equality needs
   `%.9g`/`%.17g`, never `%.Nf`.** `%.6f` silently broke 17 of 172 table keys.
3. **Verify a function boundary by disassembling forward and checking for an
   intervening `ret`.** "Nearest prologue" produced at least three false
   positives here.
4. **A caller-graph search answers "who calls X directly" and nothing more.** It
   missed a generic dispatcher one hop up, twice, and cost two reverted builds.
5. **Backups never go in the game folder** — enforced in code by
   `tools/backup_paths.py`.
6. **Dry-run (`plan`), then `apply`, then re-disassemble what is on disk.**
