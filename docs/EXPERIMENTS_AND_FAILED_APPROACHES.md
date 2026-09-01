# EXPERIMENTS AND FAILED APPROACHES

Kept deliberately. Several of these look attractive again on a fresh read, and
three of them cost multiple deployed-and-reverted builds. **A failed experiment
here is a fence, not a footnote.**

Anchors (`#f1` …) are referenced from the other documents.

---

## Resolution / GUI layer

### <a id="f1"></a>F1. UniWS "interface preset" mismatch — REFUTED

**Hypothesis.** UniWS's five interface presets are all 4:3 or 5:4, none matching
our 16:10 target, and some engine path (plausibly list hit-testing) computes its
own scale from the interface resolution rather than reading patched-canvas
coordinates. Multiple community guides recommend 1024×768 where we used
1600×1200.

**Test.** Built `tools/uniws_patch.py` from `patches.ini` and produced a
1024×768-interface build. Byte-diffed against the known-good 1600×1200 build:
**only 2 bytes differ**, exactly the bucket-selection flip.

**Result: no change — lists still unclickable.** Cleanly rules out the hypothesis.
Reverted. The port stays in the repo (correct, validated, reusable).

**Taught:** it also found a real bug in our own port — the "kept" bucket slot is
rewritten to the *actual target width*, not left at its literal default;
`patches.ini`'s "no setx" means "use the real width" (undocumented uniws.exe
behaviour).

### <a id="f2"></a>F2. `RUNASADMIN` compat flag — REFUTED

A Steam guide for a near-identical symptom pairs "disable high-DPI scaling" with
"run as administrator" as the only two recommended checkboxes. Added it.
**No effect on the click bug**, and it added a UAC prompt on every launch.
Reverted. `~ HIGHDPIAWARE` alone stays (that one is genuinely required).

### <a id="f3"></a>F3. Removing all 81 k1hrm `.gui` files — INCONCLUSIVE, and why

**Intent.** Test whether k1hrm's rescaled `.gui` set was causing the click bug by
falling back to the game's own packed layouts.

**Result: worse than the bug — main-menu text vanished and nothing at all was
clickable.** `mainmenu` is one of the resolution-bucket families, and that whole
family reports a broken flat 800×600 panel EXTENT regardless of which bucket is
loaded. Removing k1hrm's fix meant falling back to an already-broken vanilla
resource under our 2560×1600 canvas patch. The user never reached a
save/inventory screen, so the test said nothing about lists.

**Taught:** isolate the variable. The follow-up (F4) removed only the four
list-bearing files, which was the test that actually discriminated.

### <a id="f4"></a>F4. Removing only `saveload`/`inventory`/`journal`/`container` — RULED OUT `.gui`

Checked first that these have no multi-bucket siblings and are authored at plain
640×480 (305×327 for `container`), so they would render rather than blank-screen.

**Result: the click bug persisted with vanilla, non-k1hrm-rescaled `.gui` files.**
This cleanly ruled out k1hrm's rescaling as the cause and pointed at the exe.

**Also confirmed the bug's real footprint** (on files no test had touched): equip
and skills/powers/feats lists are affected too — every vertical
list-of-items screen, i.e. the bug is general to the control type.

### <a id="f5"></a>F5. The actual root cause — our own port dropped half an offset table

**This was the bug.** `hires_patcher.pl`'s `negative_offsets_x/y` hold **two
offsets per exe build**; our port flattened each pair and silently kept only the
first, dropping the list-click edit for every build, forever. Confirmed before
fixing: offsets `0xBA6C`/`0xBA83` were still at their vanilla −640/−480 defaults
in *every build we had ever produced*.

**Taught (the big one): read the upstream project's own documentation, not just
its source.** We had the Perl source the whole session and ported from it
directly, but never opened k1hrm's `README.pdf` until the user pointed at it. The
README documents the button-click and list-click edits as two explicitly separate
named steps — which a flattened array-of-pairs in the source looks identical to
correct code without.

The entire "interface preset mismatch" / "Flawless Widescreen" / "disassemble to
find the hit-test constant" investigation was chasing a decoy.

---

## HUD minimap / shared constants

### <a id="f6"></a>F6. `mapscale` rewriting the shared constants in place — REGRESSION

Enabling k1hrm's disabled `mapscale` made the Area Map fill its box and turned
the **HUD minimap black**. A/B confirmed the trade was real and isolated to that
patch.

**Taught:** `$opt{mapscale} = 0` was a **signal, not an oversight**. When
upstream disables working code, assume there is a reason and look for it first.

### <a id="f7"></a>F7. Excluding `0x29505C`/`0x295064` from scaling — WRONG, reverted

**Hypothesis.** Disassembly showed two distinct parameter pairs passed to two
different virtual calls, back to back: (512, 256) and (440, 256). Since the
minimap's box is a fixed 512×512, the (512,256) pair "must be" the minimap's own
texture size and should never scale.

**Result:** minimap still broken **and** the full tactical map regressed — it
filled its box but the room/terrain geometry vanished, leaving only grid lines
and markers. The (512,256) pair is needed by the big map too.

**Taught:** *"We hypothesised from proximity instead of proving identity."* The
disassembly observation was real; the conclusion drawn from adjacency was not.
The method that worked: search `.text` for references to the **constant's
address**, then identify each referencing function by the GUI tag strings it
binds and by its callers/vtable. That gave a definitive answer in one pass.

Both offsets are back in `MAP_OFFSETS` and scaled; the disproven idea is recorded
in `UNSCALED_MINIMAP_OFFSETS` (nothing reads it at runtime).

### <a id="f8"></a>F8. Redirecting the ARE-loader `fmul` operands — REGRESSION, TWICE

The single most expensive lesson in the project.

**The fix.** Point the four ARE-loader `fmul` operands
(`0x509D1D`/`0x509D5A`/`0x509D99`/`0x509DD8`) at the private scaled floats, so the
calibration object is built in scaled space.

**Attempt 1 (2026-08-23):** Area Map markers tracked correctly; **HUD minimap
went black.** Reverted.

**Between attempts**, an *exhaustive* clearance was performed and it was wrong:
- Unicorn emulation proved the calibration fields and the grid fields the HUD
  reads are fed by **disjoint** constructor arguments. (This part is true and
  still stands.)
- Brute-force `E8`+rel32 caller scans found `0x578C60` has exactly **one** caller
  and `0x578E00` exactly **four**, all Area-Map-owned.
- Conclusion drawn: "no code-level sharing mechanism exists; the regression was
  probably a stale-file/build mistake." **Recommended a retry.**

**Attempt 2 (2026-08-23):** markers correct again; **minimap black again** — but
with a sharper symptom: after walking around, *part* of it rendered, in the wrong
place, with a misplaced player marker. Not permanently black. Reverted; the
regressed build was kept for diffing.

**Resolution (2026-08-24, live x32dbg).** Hardware breakpoints on
`obj+0x18`/`+0x1c` **fired 100+ times during plain HUD gameplay with the Area Map
never opened.** The chain is
`0x4BABB0 → 0x4B4E80 → marker-setter cluster → 0x578E00`, i.e. a **generic,
panel-agnostic per-frame dispatcher**, one hop further up than the caller search
ever looked.

**Taught (repeatedly cited since):**
- **A caller-graph search only answers "who calls X directly."** It cannot rule
  out a shared dependency reached through a generic dispatcher one or more hops
  up. This matches documented literature: static analysis reliably misses
  indirect/vtable-dispatched callers that only appear dynamically.
- The "non-architectural, probably a stale file" explanation was a comfortable
  story that a second reproduction demolished. Two identical regressions are
  evidence, not bad luck.
- The right fix shape is a **private copy of the object handed to one call site**,
  not a redirect of anything upstream of the fork.

**Also corrected here:** an earlier overreach — "the HUD's own screen object, via
its own map-type child widget" — was asserted more confidently than the evidence
supported (nobody read the `this`/vtable identity at break time). What was
actually nailed down is narrower: *some* per-frame update reached through
`0x4BABB0` touches the object during HUD-only gameplay. The later structural
proof (both paths resolve the same `[0x7a39fc]…[+0x218]` chain) is what settled
it properly.

---

## Map-note investigation — hypotheses that did not survive

### <a id="f9"></a>F9. Icon-centering constants — REFUTED (twice, correctly)

Both note draw paths subtract a **fixed, unscaled** half-icon size
(`-0xa`/`-0xa` for the 20×20 selected icon, `-7`/`-7` for the 14×14 default) from
the transform's output. **Centring a fixed-size box on a point by subtracting
exactly half its width/height keeps the box's centre exactly on that point,
whatever the size is** — no positional error is introduced. Refuted at this site;
do not re-check.

**But it stopped one step short.** The *size* is what changed the perception: a
14 px icon was 5.5 % of the map's height in vanilla and is 1.6 % at 2560×1600 —
from a blob covering its room to a dot sitting beside it. See F13.

### <a id="f10"></a>F10. Box-origin mismatch — REFUTED

Extracted the **true vanilla** `map.gui` from `data/gui.bif` (not Override, not
k1hrm): `LBL_Map` = (95, 118, 440, 256). Patched = (380, 393, 1760, 853).
**380 = 95×4.0 exactly, 393 ≈ 118×3.3333 exactly.** The box's on-screen
*position* scales by the identical flat ratio as its size. No separate "true
centering" logic exists that could disagree with the marker math.

### <a id="f11"></a>F11. "Flat wrong scale factor, error grows with distance from origin" — REFUTED

Predicted by the hypothesis: notes far from the map's local origin should be
worst. Captured all 7 Ebon Hawk notes live and hand-calculated each predicted
pixel. **Every one falls inside the expected 1760×853 range** — none negative,
none exploding, closest to an edge is Y=813.9 against a 853 bound. The notes with
*small* world coordinates are unremarkable, solidly mid-box. Refuted.

### <a id="f12"></a>F12. Art ↔ calibration misregistration (k1hrm "Known Issue #4") — REFUTED

Deprioritised twice, then finally tested two independent ways (object point cloud
at 87.3 % floor with zero shift and no coherent peak in any scan; texture bbox
agreeing with the screenshot to ~1–3 px out of 1760). See
[ARCHITECTURE §5](ARCHITECTURE.md#art--marker-registration-is-exact).

**Taught — the sharpest methodological lesson in the project.** The 2026-08-25
"pixel-exact" test that *closed* the investigation compared the **rendered
marker** against the **predicted marker**. Both come from the same math, so it
could only ever confirm the marker code is self-consistent. **It was a
self-referential decisive test.** The conclusion it reached happened to be right;
the argument did not support it.

### <a id="f13"></a>F13. "The notes got worse because of proportional magnification" — WRONG MECHANISM

The old notes said *"the same proportional slop, now ~4× more screen pixels
wide."* **The proportional slop is invariant** — markers scale by `k` and the art
scales by the same `k`, so a marker 12 vanilla px from the floor is still 12
vanilla px (≈40 patched px) from it. What actually changed is the **fixed-size
icons** (F9). CONFIRMED by disassembly and measurement.

### <a id="f14"></a>F14. Tooltip globals `0x7A23B4..BC` / `0x7A23C0..C8` — DEAD END

Suspected of feeding a different position into the draw. Disassembled
`0x694907`–`0x694967` with widened context: the whole block is gated by
`cmp eax,[ebx+0x230]; jne 0x69498C` ("is this the selected note") and consists of
string/text-object setup calls — it builds the note's **tooltip text**, not its
map position. Do not re-check.

### <a id="f15"></a>F15. Hand-tracing the stack across ~120 branchy instructions — ABANDONED

Trying to pin the transform's Y-output frame slot statically stalled on genuine
stack-accounting complexity (conditional pushes, a `sub esp,0x10`, a call through
`[edx+0x20]` that cleans its own args). It also produced **one real arithmetic
mistake** (a claimed mismatch between the slots the transform wrote and the slots
the icon-rect code read — which the live capture later proved was our error, not
a bug) and one false lead.

**Taught:** when static tracing stalls on real complexity twice in one session —
as opposed to a heuristic false positive — **switch to a live capture** instead
of a third round of hand-derivation. The live capture answered it in one hit:
X → `[esp+0x20]`, Y → `[esp+0x10]`.

**Also from this era:** a disasm call started at an unaligned offset and decoded
*garbage-but-plausible* instructions for ~16 bytes before re-syncing. Always
disassemble forward from an already-validated address.

### <a id="f16"></a>F16. Per-module systematic delta — REFUTED (Phase 1b)

See [MAP_NOTE_PIPELINE](MAP_NOTE_PIPELINE.md#phase-1b-answered-the-error-is-per-note-not-per-module).
pooled rms 6.1 → 5.4 px. No ~90-correction shortcut exists.

---

## Delivery mechanism

### <a id="f17"></a>F17. The `.git` / `.mod` data-edit route — WORKS, BUT DISQUALIFIED

**The claim that killed it first (2026-08-25) was itself wrong.** Two research
agents asserted KOTOR caches `.git` into the save on first visit so a data edit
would do nothing for existing saves. That was **never tested** and was the single
premise justifying the exe table. The independent review flagged it as
load-bearing and unverified; Phase 1a tested it.

**Result: a `.git` edit DOES reach an existing save** — confirmed in game on two
cached modules and then **forensically**, by finding our edited floats in the
AUTOSAVE the game wrote during the test (`danm14ad` Sandral Estate
336.3313,145.3870 → 297.1678,231.4419; `danm16` Holding Cell
37.9190,51.4302 → 96.1907,85.1809). The engine read the Override `.git` and
**re-cached** the new values, so the change persists in that save even after the
Override file is removed.

**But the cost disqualifies it:** shadowing a module resource makes the engine
discard the whole cached module state. Map-exploration fog reset to unexplored in
both areas ("became hidden … revealed as if I visited it first time"), implying
containers, enemies and trigger flags reset too. **And the game crashed** once
after reloading and walking (single occurrence, cause unproven, heavily-patched
exe — hold loosely; disqualifying either way).

**The control was what made the test decisive:** a third edit on `end_m01aa`
(Endar Spire), which can never be in an existing save. Without it, "nothing
moved" would have been ambiguous between "saves cache" and "Override is not a
`.git` delivery path in K1 at all".

**Also disqualifying for `.mod`:** a `.mod` **fully supersedes** the module's
RIM pair rather than layering, a documented conflict category, and must contain
every resource from **both** the `.rim` and `_s.rim` (one modder traced a module
load hang to a forgotten `.are`).

**Reversibility asymmetry, proven:** a data edit gets re-cached into the save
**permanently** — removing the Override file did not undo it; the save had to be
restored from backup. The exe route leaves nothing in saves at all.

**Retained value:** the data-edit route is clean for **new playthroughs** and
remains a reasonable optional extra (a HoloPatcher `[GFFList]` field patch is the
right *form* of data edit; K1CP patches `XPosition`/`YPosition` in a `.git`
exactly this way). `tools/make_git_edit.py` is the working prototype.

### <a id="f18"></a>F18. Growing `LBL_Map` to hide the frame line — FAILED TWICE, REVERTED

**Goal.** Remove the thin light-blue line on the Area Map's top/left/right.

**Diagnosis (correct).** `LBL_Map` has no BORDER at all (`edge=''`, `corner=''`,
`fill=''`). The line is a **1-pixel border baked into the panel background art**
`lbl_map`, drawn around a 640×480 panel where one art pixel is one screen pixel.
Stretched to 2560×1600 it becomes several. Measured:

```
left   x 376..379  (4 px)      right  x 2140..2141 (2 px)
top    y 391..392  (2 px)      bottom y 1246 present but (0,7,33) - invisible
```

**Attempt 1:** grow the box to cover the line — (380,393,1760,853) →
(376,391,1766,855). Top/left/right cleared; **the bottom line appeared.**
Diagnosed as an off-centre growth (4 left, 2 up, 2 right, 0 down moves the centre
~1 px up-left).

**Attempt 2:** grow every side by 4 px symmetrically → (376,389,1768,861), centre
unchanged at (1260, 819.5).

**Result: worse, and the diagnosis was wrong.** Sandral Grounds gained a bright
**orange** line down the right (x 2137..2143, full map height) plus a bright blue
band at y 1234..1245. The user confirmed it was new.

**Actual root cause.** The engine draws the 440×256 map texture into the box by
**clamping at the texture edge**, so *any* box growth smears the texture's last
row/column across the extra pixels. Whether the smear is visible depends entirely
on the map's edge colour:

```
m14ad (Sandral Grounds)  last col (87,56,13), last row (90,56,16)  -> ORANGE, visible
m12aa (Ebon Hawk)        last col (0,0,0),    last row (0,4,0)     -> black, invisible
```

Attempt 1 only *appeared* to work because Ebon Hawk's map edges are black.
**Symmetric vs asymmetric growth was never the real variable.**

Checked before concluding: across all 88 map textures the last drawn column
(x=439) is **not** anomalous anywhere — largest deviation game-wide is `m01ab` at
17.0 mean, nothing above 20. So the orange was revealed *map art*, not a bad
pixel column.

**Reverted at the user's request.** `Override/map.gui` is byte-identical to the
original (md5 `4a9b423f4bf823f3b69405e0decf1e0f`).
`tools/map_frame_fix.py` is kept for its measurements and root-cause write-up but
**must NOT be applied again as-is**.

**Taught:** the box may not be grown in any direction. The only fix that does not
disturb the map render is editing the art — see [FUTURE_WORK](FUTURE_WORK.md).

### <a id="f19"></a>F19. Adding a 5th PE section — REJECTED before attempting

Section headers must be a contiguous array, so a 5th header lands at file offset
`0xAA8`..`0xACF` and **`0xAC0` holds a 16-byte `Hellspawn Reborn` watermark** from
a third-party patcher (absent from the pristine Steam exe; written by none of our
tools). That tool may read its own marker to decide whether the exe is already
patched. Growing `.rsrc` achieves the same thing with three header fields and no
new header. See [FIX_IMPLEMENTATION](FIX_IMPLEMENTATION.md#pe-section-space).

**Related caution for shipping:** "a section was appended to an executable" is
itself an antivirus heuristic trigger. Weigh it if we ever package for others.

---

## Smaller rejected ideas, kept so they are not re-proposed

### <a id="f20"></a>F20. "A note within 3 px of a waypoint was placed deliberately"
Measured: half the matching waypoints are incidental NPC patrol/spawn points.
Does not discriminate. Not added. (Details in
[MAP_NOTE_PIPELINE](MAP_NOTE_PIPELINE.md#review-and-the-bugs-looking-found).)

### <a id="f21"></a>F21. bbox-fill ≥ 0.25 to reject diagonal line segments
Worked, but superseded by the PCA true-normal rule which handles diagonals
properly instead of discarding them. Chosen over an aspect-ratio test, which
would have discarded the small compact path-end markers that were producing good
results.

### <a id="f22"></a>F22. DXWnd for debugger-safe windowed mode — DROPPED as unnecessary
The user already runs KOTOR windowed reliably, which satisfies the same goal
without a new third-party tool. Do not re-suggest unless windowed mode itself
turns out to cause instability. (x32dbg also has a documented *unrelated*
hang-on-breakpoint bug.)

### <a id="f23"></a>F23. `sed`/`python -c` string replacement across the tools
Two of the tool files are CRLF and the rest LF, so shell-level replacement kept
missing patterns that were visibly identical. **Use the editor tooling for these
files.**

### <a id="f24"></a>F24. Migrating our patches to Kotor Patch Manager — DECIDED AGAINST (revisit if we publish)

**Adopted partially:** the address database only (`reference/kpm/`).

Against migrating:
1. **It cannot do what we need.** A comprehensive K1 widescreen patch is KPM issue
   #19, open since 2025-11-18 and unstarted; there is no UniWS/k1hrm equivalent
   and no map-marker work. We are ahead of it in this domain.
2. **Runtime injection changes the deployment contract.** The game must launch
   through `KPatchLauncher` (or a `binkw32.dll` proxy on Wine/Proton). Today our
   patched exe just runs from Steam.
3. **Its conflict detection is weaker than we'd need** — `HookValidator` groups by
   exact address equality only, so two patches taking overlapping byte ranges
   from different start addresses are not detected. No cave allocator, no
   used-region tracking.
4. `PathHelpers.GetBackupPath` writes backups **inside the game folder**, which
   our `CLAUDE.md` forbids and Steam's "verify integrity" would eat.

What migrating would buy, if we ever do it: cave space stops being a constraint
(REPLACE hooks `VirtualAlloc` at runtime; KPM ships a 1,462-byte block
precedent); per-hook `original_bytes` verification with atomic install failure;
**it can patch the packed Steam exe** (injection happens after the DRM stub
decrypts `.text`), which our approach fundamentally cannot; and coexistence with
37 K1-capable patches via manifest `requires`/`conflicts`.

Migration cost is lower than expected — `SIMPLE` hooks have no size limit, so
each cave could go in as one simple hook whose `original_bytes` is the all-zero
region (**the zero check becomes our cave verification**), no C++ compiler
needed. The *idiomatic* route is a real rewrite: `ApplyReplaceHook` is a plain
memcpy with **no relocation pass**, and 32-bit x86 has no RIP-relative
addressing, so our cave asm (parameterised on the table's absolute VA) could not
reference its own table without a call/pop EIP trick or being rewritten as a C++
detour.

**Bug worth reporting upstream** (found and independently verified): KPM's
`BorderlessFullscreen` declares `kotor1_steam_103` support for a `static` hook
whose `original_bytes` (`BE 00 00 CF 02` at VA `0x44DC0C`) **cannot verify on the
Steam exe** — ours has a `.bind` section and holds `68 31 3C D9 95` there. A
static on-disk hook cannot work on the packed exe by construction.

**Unresolved:** whether KPM's runtime hooks work end-to-end on the packed Steam
exe was never tested (nobody ran the launcher). Release 0.6.0 claims "apply
patches after runtime decryption", but the author concedes on DeadlyStream that
at least one patch fails on Steam because init runs before the attach window.

---

## Investigations that produced a *correct* conclusion from a *bad* argument

Worth separating from outright failures, because the conclusions still stand:

| conclusion | why the original argument didn't hold |
|---|---|
| "the note drift is not a bug in our patch" | reached by elimination without eliminating art registration (F12) |
| "notes got worse at high resolution" | right observation, wrong mechanism (F13) |
| "Cargo Hold and Swoop are the same phenomenon as Engine Room, smaller" | unjustified extrapolation from one note; measured, **six of the seven Ebon Hawk notes are on or immediately adjacent to their room's floor** — only Engine is genuinely off |
| "the exe-side table is the right delivery mechanism" | originally justified by an untested save-caching claim that turned out false (F17); the conclusion survived on entirely different grounds |

## Measured per-note reality check (Ebon Hawk)

Art measured in an annulus around each marker (r = 11..20, outside its own icon):

| note | box-local | floor / hull in annulus | dist to floor |
|---|---|---|---|
| PortQuarters | (523, 327) | 81 % / 18 % | ≤7 px (icon-limited) |
| Starboard | (1277, 306) | 69 % / 30 % | ≤7 px |
| sw_exit | (1096, 367) | 100 % / 0 % | ≤7 px |
| Cargo | (578, 573) | 58 % / 41 % | ≤7 px |
| Cockpit | (911, 58) | 47 % / 52 % | ≤7 px |
| Swoop | (1136, 605) | 50 % / 50 % | ≤7 px |
| **Engine** | **(867, 814)** | **0 % / 99 %** | **40 px (12 vanilla px)** |

`7 px` is the floor of what the method can measure — the icon itself covers the
art within r ≤ 6. For reference, the module's own `enginehum` sound emitter —
BioWare's own marker for where the engines are — projects to box-local
**(868, 763)**, on floor, 51 px above the note at the same X; the walkable floor
at that X ends at box-local y ≈ 774 and the note is at 814.

## The vanilla A/B — six items attributed in one test

Ran the pristine Steam exe, empty Override, 1600×1200 (chosen over 1024×768 to
keep the pixel count in the same league; a lower resolution would flatter vanilla
for the wrong reason). `tools/vanilla_toggle.py` makes the round trip
deterministic; Override is **renamed**, not re-copied, so the restore is exact by
construction.

| item | vanilla behaviour | verdict |
|---|---|---|
| notes drift / wrong side of line | **present**; Engine Room is outside the walkable area in vanilla too | BioWare data. 4th independent confirmation our patches are innocent |
| player marker imprecise | **present**, minimap AND area map | engine baseline; our double-rounding is a separate, smaller addition |
| blue lines with no note | **present** | vanilla content; unfixable via our table |
| diagonal transition notes | **present**, "all over the place" | BioWare data |
| stutter after closing area map | **present** | engine behaviour. **CLOSED — not ours** |
| map frame bottom border | vanilla Ebon Hawk has **no border either** | not ours |
| item icon "broken outline" | **reinterpreted** | it is the stack-count badge with no number — **ours**, and the only real regression the A/B found |

Also confirmed: **7 notes in the Ebon Hawk in vanilla**, same as modded — so the
note that never draws is vanilla `HasMapNote` data, not our table dropping one.

**The stack-count number**, run to ground: the count is **not a GUI control**
(walked every control in the vanilla inventory/container/equip/upgradeitems/
questitem/store/abilities/character `.gui` — zero count/stack/qty-tagged
controls; the only `LBL_COUNT` in the whole set is in `partyselection.gui`).
Control counts are identical between vanilla and our Override copies, so our
rescale added or dropped nothing. The number is drawn by **engine code** onto the
icon quad, which makes the **font** the load-bearing input:

| font | vanilla | Override | delta |
|---|---|---|---|
| `fnt_d16x16b` | 512×512, height 0.19, baseline 0.15 | 512×512, height **0.32**, baseline **0.32** | +68 % tall, baseline moved |
| `dialogfont16x16(b)` | 256×256, 0.16/0.16 | 448×448, 0.28/0.28 | +75 % |
| `dialogfont10x10b` | 256×256, 0.16/0.16 | 512×512, 0.22/0.22 | +38 % |

**Bisected by group** (`tools/font_test.py off`), 12 files parked → **the number
came back**. Restored. Diagnosis complete: the *Larger Text Fonts* mod's digits
no longer fit the engine's fixed-size badge. There is precedent from the same mod
in this project's own manifest — `savefont16x16b` at *Menu_VeryBig* overflowed
the save-slot hitboxes and had to be downgraded. **The user chose to keep the
bigger fonts and forgo stack counts.** Which of the six fonts is responsible was
deliberately never bisected; if revisited, pull `fnt_d16x16b` first (default HUD
font, and the only one whose baseline also moved).

### <a id="f25"></a>F25. `hires_patcher.exe` leaves the Area Map centring constants at 640/480 — **ROOT-CAUSED 2026-08-30. NOT OUR BUG.**

**Found by the first Phase 4 Tier A pass (1920×1080). The defect is in the
prerequisite, k1hrm's own compiled patcher — our layer is correct.**

**Symptom.** In game the Area Map art was displaced down-right, overflowing the
screen, while the `LBL_Map` box itself sat correctly. Note markers, HUD minimap,
player/party markers and open/close all passed. All 19 of our post-write checks
passed, and `Override/map.gui` matched the exe.

**Measurement (numpy, on `downloads/swkotor_EZ07Hn8Jng.png`).** Map tile pitch
was **66.0 px = 1320/20** horizontally and **52.4 px = 576/11** vertically — i.e.
the art was *correctly scaled* from our private floats. Its origin was
**(927, 566)** against a box origin of **(285, 266)**: a displacement of exactly
**(642, 300)**. For contrast, the confirmed-good 2560×1600 screenshot puts the
texture at exactly **x 380..2139, y 393..1245** — pixel-perfect on its
(380, 393, 1760, 853) box, displacement **(0, 0)**.

**Root cause.** `0x6928B3`/`0x6928C3` and `0x692959`/`0x69296B` are int16
immediates inside the map GUI code:

```
0x692958  sub eax, 0x280      ; 640
0x69295D  cdq / sub eax,edx / sar eax,1   ; signed /2
0x692964  add esi, eax        ; esi += (screenW - 640)/2
0x69296A  sub eax, 0x1e0      ; 480  -> edi += (screenH - 480)/2
```

They are k1hrm's `positive_offsets_x` / `positive_offsets_y` (gog set
`[0xAA65, 0x292959, 0x2928B3]` / `[0xAA85, 0x29296B, 0x2928C3]`). k1hrm is
supposed to overwrite 640/480 with the target resolution so the centring term
becomes **zero**. Left at 640/480 it evaluates to
`((1920-640)/2, (1080-480)/2)` = **(640, 300)** — the measured displacement.

**Why it happened: `hires_patcher.exe` and `hires_patcher.pl` do not agree.**
Patching the same UniWS-only 1920×1080 base, letterbox off:

| tool | `0xAA65` | `0x292959` | `0x2928B3` |
|---|---|---|---|
| `hires_patcher.pl` (perl) | 1920 | **1920** | **1920** |
| `hires_patcher.exe` (shipped, what `hires_patcher.bat` runs) | 1920 | **640** | **640** |

A full byte diff of the two outputs is **exactly 6 bytes**, all four map sites,
nothing else. Reading `hires_patcher.pl` shows no resolution- or aspect-dependent
branch that could explain it — detection pushes any offset whose current value
equals the default, and the write phase writes every pushed offset — so the
shipped `.exe` is evidently built from an **older revision** of the script, before
those two offsets were added to each list.

**This is resolution-independent.** The earlier framing of this finding as a
resolution-specific regression was wrong. The real variable is *which k1hrm tool
ran*: our 2560×1600 build came from `tools/hires_patch.py` (which follows the
`.pl`, and Phase 1 proved byte-identical to it), while this 1920×1080 build was
the first ever made with the shipped `.exe`.

**Why this matters a great deal for our release.** k1hrm's README and its
`hires_patcher.bat` tell Windows users to run the **`.exe`**. So the *documented,
normal* Windows install of our own stated prerequisite produces an exe that
renders our headline feature wrong — and it looks like our bug, not k1hrm's.
Our patcher must detect these four sites and refuse (or loudly warn) rather than
patch on top; see [RELEASE_PLAN](RELEASE_PLAN.md) §5.1. Phase 3's offline QA
could never have caught this: it builds its test binaries through
`steps.apply_all` on a `.pl`-equivalent base, so the broken input never occurs.

**Fix for a user already in this state:** re-run k1hrm from the UniWS-only exe
using `perl hires_patcher.pl W H no swkotor.exe`, or patch the four int16 sites
directly. Not fixable by reinstalling our mod.

**Found in the wild — CONFIRMED 2026-08-30 (Phase 5).** The defect is not
hypothetical and not confined to this machine: the published third-party mod
**"KotOR 3440×1440 Enhanced v1.1"** ships a **pre-patched `swkotor.exe`**
(4,042,752 bytes) that carries it. Read straight out of that file:

| site | value | should be |
|---|---|---|
| canvas `0xB6C7` / `0xB6DA` (file offsets) | −3440 / −1440 | correct |
| centring `0x2928B3`, `0x292959` | **640**, **640** | 3440 |
| centring `0x2928C3`, `0x29296B` | **480**, **480** | 1440 |

`detect.centring_state()` returns `"stale"` on it — the exact fixable-stale state
§5.1 was built for, so our patcher repairs it rather than refusing. Two
consequences: the state we handle is one real users are already shipped into by a
mod that has nothing to do with us, and this is a second, independent witness for
the upstream report to ndix UR.

### <a id="f26"></a>F26. `hires_patcher.bat` invokes `hires_patcher` by bare name — no path, no `.exe` — CONFIRMED 2026-09-01

Found live during the user's clean-GOG acceptance test. The shipped wrapper is:

    hires_patcher %WIDTH% %HEIGHT% %LTRBOX% %EXE%

No path, no extension — Windows resolves it only via cwd or `PATH`. Launching the
`.bat` with "Run as administrator" resets cwd to `System32` on this machine (a
known Windows elevation quirk, not ours), so the four `set /p` prompts all work
(they're pure batch) and only the final line fails: `'hires_patcher' is not
recognized...`. Nothing gets written to the exe when this happens — the failure
is before the patcher runs, so it's a clean no-op, not a partial patch. Fix for a
user in this state: re-run the `.bat` with a plain double-click from inside
`k1hrm-1.5/`, not elevated.

**This is the second independent k1hrm defect this project has hit** (see F25 —
`hires_patcher.exe` vs `.pl` disagreeing on the centring constants). Both are in
the *documented, normal* Windows path (`.bat` → `.exe`), not an edge case.
**Open question raised by the user 2026-09-01: is k1hrm reliable enough to keep
as a required prerequisite, or should Phase 7 scope a from-scratch replacement
for the GUI-layout patching k1hrm does** (the per-resolution `.gui` file
generation), separate from the engine-level UniWS step which has never shown a
defect? No decision yet — needs weighing against the size of k1hrm's own
resolution-set coverage (49 sets) that we'd be reimplementing. Tracked in
`STATE.md`.

