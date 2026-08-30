# SHIPPING — packaging and distributing this to the community

Researched 2026-08-28. **Nothing has been built or published yet.** This is the
brief for whoever does it.

## What we would actually be shipping

Two logically separate mods, and they should probably ship separately:

1. **A widescreen/resolution patch** — UniWS gate + canvas + list-click +
   `mapscale` + the minimap float redirect + the three marker caves. This
   overlaps heavily with existing community tools (UniWS, k1hrm) and its novel
   part is that `mapscale` **actually works** and the Area Map markers are
   correct — which upstream never shipped.
2. **The map-note correction table** — 250 corrections keyed on world position.
   **This has no counterpart anywhere.** KotorUniResPatch does not touch note
   placement at all; BioWare's misplaced coordinates are scaled along with
   everything else and stay wrong. This is the genuinely new contribution.

The note table is **resolution-independent by construction** and touches no game
data, so it is the easier and safer of the two to ship, and it is useful to
players who never change resolution at all.

## Hard constraints

- **Do NOT redistribute a pre-patched `swkotor.exe`.** DeadlyStream terms forbid
  piracy; Nexus submission guidelines require respecting the game's licence.
- **TSLPatcher / HoloPatcher cannot touch the exe** — TLK/2DA/GFF/SSF/NSS only.
  They are the wrong tool for our main deliverable (though right for an optional
  data-edit variant, see below).
- Our patch requires the **"KOTOR Editable Executable"** (DeadlyStream #1320,
  ~399k downloads) as a prerequisite, because the packed Steam exe cannot be
  statically patched. That is the assumed baseline for this whole class of mod.

## The community norm: ship a patcher, not a patched exe

Precedents, all small standalone patcher `.exe` + `Apply X.bat` / `Revert X.bat`
dropped next to `swkotor.exe`, self-backing-up:

- K1 Marked Empty Containers (DS #3006)
- Fair Pazaak Turn Order (DS #2996)
- K1 Ultrawide Letterbox Fix (DS #2993, ShaeMyName — also Nexus #1809)
- k1hrm itself (DS #1159 — `hires_patcher.bat`/`.exe`/`.pl`, a frozen Perl script)

**Shape to build:** a frozen Python patcher (PyInstaller) + `Apply.bat` /
`Revert.bat`, **and ship the `.py` source alongside**. The Ultrawide Letterbox Fix
does exactly that and words it as *"if you'd rather not trust an executable, you
can run the patch yourself using Python"*. k1hrm goes further and **documents its
raw hex offsets** so a user can patch by hand if the patcher fails — worth
copying; it is our escape hatch for exe variants we don't support.

## Install order is fixed by the community's own guides

```
Editable Executable  ->  swkotor.ini / swconfig  ->  UniWS  ->  k1hrm  ->  OURS LAST
```

Our caves live in spare `.text`, and UniWS/k1hrm both write into `.text`/`.rdata`,
so applying last **and verifying expected pre-state bytes (refuse, don't
corrupt)** is required. Our patchers already verify original bytes and refuse to
double-apply — that discipline is a shipping feature, not just hygiene.

**TODO before shipping: document the exact cave byte ranges we occupy**
(`0x73C1D0`–`0x73C2A9` and the `.rsrc` region at `0x86D000`) so a future collision
with another exe patcher is diagnosable by someone who isn't us.

## Hazards to warn users about

| hazard | mitigation |
|---|---|
| **Steam "verify integrity" deletes the swapped exe** | tell users to keep a copy of the patched exe outside the install |
| **PyInstaller one-file builds get flagged by antivirus heuristics** | ship source + a published SHA-256; consider `--onedir` |
| **Appending/growing a PE section is itself an AV heuristic trigger** | this is our `pe_space.py` step. Weigh it against the DLL route below; at minimum, publish hashes and explain what it does |
| **Exe variants differ** | GOG / 4-CD v1.03 exes are directly patchable, but their free `.text` space is **not guaranteed** to match the Editable Exe's. **Fingerprint the target before writing and state which build we support** rather than probing |

## The DLL alternative, and a correction to an earlier assumption

**CORRECTION to an earlier note in this project:** `binkw32.dll` is **not** the
DLL slot KOTOR 1 mods generally occupy. The live ASI-proxy precedent is
**`dinput8.dll`** (True Controller Support, DS #2972 — ships `dinput8.dll` +
`K1Controller.asi` + `SDL2.dll`). KPM only stages a `binkw32.dll` proxy on
Wine/Proton; on Windows it injects at runtime and stages no proxy at all.
`opengl32.dll` is taken by GLIntercept.

So the DLL route has a **smaller conflict surface on Windows than assumed**, and
it does not weigh against KPM as much as an earlier note implied.

**DLL injection works on the packed Steam exe**, needing no Editable Executable
at all. That remains the single strongest argument for the DLL route, and it
would roughly double the addressable audience.

Against it: it changes the deployment contract (the game must launch through a
launcher or proxy), and our cave asm is parameterised on the table's absolute VA,
which a plain memcpy-style REPLACE hook cannot relocate — see
[failures F24](EXPERIMENTS_AND_FAILED_APPROACHES.md#f24) for the full migration
analysis.

**Kotor Patch Manager is still niche**: 665 total GitHub downloads lifetime.
Shipping *only* as a KPM patch would reach far fewer people than a standalone
patcher.

## An optional data-edit variant, for new playthroughs only

A HoloPatcher `[GFFList]` field patch on `XPosition`/`YPosition` is the *right
form* of data edit and has direct precedent (K1CP patches those exact fields in a
`.git`). It is **clean for new playthroughs** and needs no exe patching at all.

It is **not acceptable for existing saves** — proven in game: it works, but only
by discarding that module's cached state (exploration fog reset; one crash). See
[failures F17](EXPERIMENTS_AND_FAILED_APPROACHES.md#f17).

If shipped, it must be labelled unambiguously as new-game-only, and
`tools/make_git_edit.py` is the working prototype.

## Suggested release checklist

1. Decide the split: note table alone first (lower risk, novel, resolution-free),
   widescreen bundle second.
2. Fingerprint supported exe builds explicitly; refuse anything else with a clear
   message rather than probing for free space.
3. Freeze the patcher, ship source alongside, publish SHA-256 of both.
4. Document the raw offsets and cave ranges in the README (k1hrm precedent).
5. `Apply.bat` / `Revert.bat`; backups go **outside** the game folder, and say so.
6. State the install order and the Editable Executable prerequisite.
7. Warn about Steam integrity verification.
8. Credit: k1hrm (ndix UR) for the GPLv3 patcher we ported — **check the GPL
   implications of shipping a port before publishing**; UniWS/wsgf; PyKotor;
   LaneDibello's KPM address DB (MIT, and its LICENSE is already vendored at
   `reference/kpm/LICENSE.kpm`).
9. **Licence review is an open item** — see [FUTURE_WORK](FUTURE_WORK.md).

## Licence facts already established

- **k1hrm's `hires_patcher.pl` is GPLv3.** `tools/hires_patch.py` is a port of it.
  This has direct consequences for how we may licence and distribute our patcher.
  **Not yet resolved.**
- **J0-o/KotorUniResPatch has NO licence** (`"license": null`, no LICENSE file) =
  all rights reserved. The addresses and constants are facts about the game binary
  and ours to use; **their C++ source text is not.**
- **KPM is MIT.** Its address database is vendored with its LICENSE.
- UniWS is a long-standing legitimate tool from wsgf.org; we reimplemented its
  patch from its own plaintext `patches.ini`.
