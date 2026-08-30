# FIX IMPLEMENTATION — exactly what we changed and why it works

Five separate patches, applied in this order. Each is self-verifying: it refuses
to run unless the current bytes match what it expects.

---

## <a id="layer-1"></a>Layer 1 — engine resolution gate (UniWS)

**Problem.** The exe hardcodes which resolutions it accepts; 2560×1600 is
rejected regardless of `swkotor.ini`.

**Why not the Steam exe.** Its `.text` entropy is **8.00** — encrypted at rest,
real code only exists in memory after a runtime unpacker. It cannot be
statically patched. We use the **"KOTOR Editable Executable"** (FairLight-cracked
pre-Steam-DRM v1.03; `.text` entropy 6.50, PE timestamp Feb 2004, no suspicious
API strings — checked before use). That trade-off was made deliberately, not
silently.

**What.** UniWS rewrites the resolution-gate comparison
(`cmp eax,800 / cmp [esp+8],600`), plus two "movies" edits. Signature
`3D20030000EFEFEFEFEFEF58020000`, verified to match exactly one location.
Interface preset **1600×1200**.

**Our port:** `tools/uniws_patch.py`, written from `patches.ini`'s plaintext
signature format and byte-diff-verified against the official tool's output —
only 2 bytes differ across the whole 4 MB file, both the expected bucket-flip.

**Verified:** the undo files show all 6 sub-patches hit the expected old values
(800, 600, 1024, 1280, 1600, 640, 480) at every predicted offset.

> The interface preset is **irrelevant to the list-click bug** — tested 1600×1200
> and 1024×768, no difference. See [failures](EXPERIMENTS_AND_FAILED_APPROACHES.md#f1).

---

## Layer 2 — the 640×480 canvas + the list-click fix

**Problem.** With the gate open, all 2D UI renders correctly-proportioned but
confined to a small unstretched box in the top-left, because the 2D GUI/camera
system bounds itself with hardcoded ±640/±480 constants.

**What.** `tools/hires_patch.py` (our from-scratch Python port of k1hrm's GPLv3
`hires_patcher.pl`, read in full rather than trusted blind) overwrites those
constants with the real target width/height at known file offsets, only where the
current bytes match the expected vanilla default.

**The critical detail** — k1hrm's README documents **three separate** hex edits,
not one combined "canvas patch":

| edit | ~offset (gog) | what it fixes |
|---|---|---|
| first | `0xB6C7` (X) / `0xB6DA` (Y) | *"being able to click menu buttons"* |
| **second** | **`0xBA6C` (X) / `0xBA83` (Y)** | ***"being able to scroll and click list items (like save games)"*** |
| third | `0xAA60`-ish | load-screen positioning |

Our port had flattened `negative_offsets_x/y` from an array-of-**pairs** down to
one offset per build, silently dropping the second (list-click) edit for every
build. Fixing that fixed the bug. Final tables in
[REVERSE_ENGINEERING](REVERSE_ENGINEERING.md#patcher-offset-tables-file-offsets-from-hires_patchpy).

**Verified:** both offsets read back as −2560/−1600; the patch reports **2
matches** per axis instead of 1. CONFIRMED in game — every list screen clickable.

**Also patched here:** DPI. Windows DPI scaling (150 % on this machine) cropped
the 3D view to the top-left ~40 %. Fixed with `~ HIGHDPIAWARE` in
`HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers`.
Still required. (`RUNASADMIN` was also tried, does nothing for the click bug,
and was reverted — it only adds a UAC prompt.)

---

## Layer 3 — `mapscale` and the HUD minimap split

**Problem 1.** The tactical Area Map doesn't fill its box. k1hrm ships a
fully-implemented `mapscale` path **hardcoded off** (`$opt{mapscale} = 0`,
set unconditionally right after arg parsing; never exposed as a CLI flag).
The author wrote it end-to-end then permanently disabled it before shipping.

We ported it anyway (`patch_map_scale()` / `find_map_matches()`), replicating the
original's formulas — 17 int16 sites. **Verified:** 20 of 21 target offsets
matched their known defaults; `map_grid` didn't and was correctly left alone.

**Problem 2 (caused by problem 1's fix).** The Area Map was **off-centre to the
right** by 288 px. Cause: a faithfully-replicated quirk — `map_offsets_x` and
`map_offsets_float_x` were scaled by the same `width*(512/640)` ratio as
`map_projection_offsets_x`, although their own default (440, not 512) implies
`width*(440/640)`. That line is dead code in the original (overwritten before
use). Fixed by giving them their own 440/640 ratio; `map_projection_offsets_x`
keeps 512/640 because that matches *its* default. 2048 → 1760. CONFIRMED in game.

**Problem 3 (also caused by problem 1's fix).** The **HUD minimap rendered
black**.

Root cause, proven by disassembly rather than hypothesis:
- The HUD map draw (`0x688100`) and the Area Map draw (`0x6943D0`) both do the
  identical tile-size math, `440.0 / gridCountX` and `256.0 / gridCountY`,
  reading the **same two shared constants** `0x747748` / `0x7455D4`.
- `mapscale` rewrote those constants **in place**, so it necessarily rescaled the
  minimap too.
- But the minimap's own box (`LBL_MAP` in `mipc*.gui`) is a **fixed 512×512 in
  every one of the four vanilla resolution buckets** — it was never meant to
  scale. So its tiles were drawn at full-screen scale inside a small fixed box,
  landed outside it, and the minimap went black with only the player marker (drawn
  by separate position-clamped code) still visible.

**In-place constant patching cannot fix one without breaking the other.** That is
almost certainly the real reason upstream shipped `mapscale` disabled.

**The fix — `redirect_bigmap_floats()`, and the pattern that generalises:**

1. Write **private** scaled copies `1760.0` / `853.33` into verified-free,
   4-byte-aligned `.rdata` tail padding at **`0x78CC00` / `0x78CC04`**
   (1026 verified-zero bytes there).
2. Rewrite **only** the two `fdivr dword ptr [...]` disp32 operands inside the
   Area Map's own draw method (`0x6944A8` / `0x6944C4`) to point at those copies.
3. The HUD keeps reading the untouched shared originals.

Every step is gated: refuses unless the shared constants are still vanilla, the
destination slots are zero, and each operand currently points at the expected
shared constant. **Verified:** only **17 bytes** differ from the previous
known-good exe; shared constants still read 440.0/256.0; the HUD instructions
still read `[0x747748]`/`[0x7455d4]`. CONFIRMED in game.

> **This is the pattern to reuse:** redirect the *consumer's operand* to a
> private copy; never rewrite a shared constant in place.

---

## Layer 4 — Area Map marker fixes (three code caves)

### 4a. Note markers — private calibration object (`0x73C1D0`, 60 B)

**Problem.** The ARE loader bakes the *vanilla* 440×256 pixel space into
`obj+0x18..0x24`, so markers compute into roughly the 0..440 / 0..256 range —
which still passes the (correctly widened) 1760/853 bound check, so they render,
squeezed into a small square in the top-left corner.

**Why not redirect the loader's four `fmul` operands** (the obvious fix, tried
twice): the calibration object is a **shared singleton** read by the HUD through
a generic per-frame dispatcher. See
[failures](EXPERIMENTS_AND_FAILED_APPROACHES.md#f8) — this is the single most
expensive lesson in the project.

**The fix.** Hook the **one** genuinely Area-Map-owned call site with a 5-byte
`jmp` at `0x6946D3` → cave at `0x73C1D0`, which:

```
mov esi, eax                 ; source = the live shared object (arrives in eax)
lea ebx, [esp-0x400]         ; scratch destination
rep movsd  x10               ; copy the full 0x28-byte object
fld [ebx+0x18] / fdiv [kx] / fstp [ebx+0x18]     ; X scale /= 4.0
fld [ebx+0x1c] / fdiv [ky] / fstp [ebx+0x1c]     ; Y scale /= 3.3333
mov eax, ebx                 ; hand the private copy back as the object pointer
<restore registers, reproduce the two replaced instructions>
jmp 0x6946D8
```

Offsets `+0x20`/`+0x24` are **copied but never written** — per the invariance
algebra (`scale' = scale/k`, `offset' = offset` exactly). The other three callers
of `0x578E00` are untouched.

**Verified:** disassembled by hand instruction-by-instruction against the design;
correct axis pairing, no swapped registers, no off-by-one in the copy count.
CONFIRMED in game.

**Known latent hazard:** `lea ebx,[esp-0x400]` borrows stack **below ESP**. Win32
x86 has **no red zone** — exception dispatch and user-mode APCs can write there.
The window is short and it has never misbehaved, but `sub esp, N` would be
strictly safer. Recorded as a hazard, *not* as a general lesson.

### 4b/4c. Player and party markers (`0x73C20C`, 38 B; `0x73C232`, 49 B)

**Problem.** Player/party positions are **not** computed per-draw. They are
computed once per frame into a cache and read back by `0x5791B0`, which returns
still-vanilla-space integers. The notes fix cannot touch them.

**The fix.** Rescale at the **read site**, before the existing centring
subtraction, reusing the kx/ky constants the notes fix already wrote — no new
float constants, no calibration work, and neither hook touches `0x578E00` or
anything the generic HUD path reaches, so this class of fix **structurally
cannot** repeat the minimap regression.

| | hook | bytes | cave | resume |
|---|---|---|---|---|
| party loop | `0x694A42` (`mov ecx,[ebx+0x64]` + `test ecx,ecx` = exactly 5 B) | 5 | `0x73C20C` (38 B) | `0x694A47` |
| player | `0x694AB1` (`test eax,eax` + `je 0x694B1B` + `mov ecx,[esp+0x18]` = 8 B; 12 taken, 5 jmp + 7 NOP) | 12 | `0x73C232` (49 B) | `0x694ABD` |

Each cave does `fild` / `fmul [0x78CC08 or 0x78CC0C]` / `fistp` on `[esp+0x14]`
(X) and `[esp+0x18]` (Y), then reproduces the replaced instructions. The player
cave reproduces `test eax,eax; je` **first**, because that flag comes from the
call's untouched return value and must survive unclobbered.

**Before writing anything**, the one open caveat was closed: all 59 branch
instructions in the containing function plus a file-wide absolute-reference
search were checked against both hook windows' interior bytes
(`0x694A43`–`0x694A46`, `0x694AB2`–`0x694ABC`) — **zero hits**, nothing jumps
into the middle of either replaced block.

**Verified:** dry-run on a disposable copy first, byte-exact readback, then the
real install. CONFIRMED in game 2026-08-24 — both marker types track correctly,
minimap unaffected.

---

## Layer 5 — the map-note correction table

**Problem.** BioWare's own authored `XPosition`/`YPosition` for map notes are
wrong across most of the game. Our patches are innocent — confirmed four
independent ways, most decisively by the vanilla A/B (the Engine Room note is
outside the walkable area in vanilla too).

**Why an exe table and not a data edit.** See
[ARCHITECTURE §7](ARCHITECTURE.md#7-save-game-caching-decides-delivery-mechanism).
A `.git` edit *does* reach existing saves, but only by discarding that module's
cached state (exploration fog reset; one crash). The exe table serves existing
saves and new games identically, touches no game data, and leaves nothing in
saves — restore the exe backup and the install is stock.

### The hook — a NEW 5-byte site, existing caves untouched

`0x6946EF` + `0x6946F2` is **exactly** a 5-byte window with no straddling
(`89 4a 08 8b c8`), so this gets its own hook and the three verified marker caves
are not touched. Better than the review's "extend the notes cave" suggestion:
same effect, no risk to already-working code.

The correction is written to the **stack copy** at `[edx]`/`[edx+4]`, so the
note's own data in memory is never modified. Only this call site is patched;
player/party markers never pass through here, so they **cannot** move — that
satisfies `CLAUDE.md`'s rule by construction, not by luck.

### The match routine (`0x73C270`, 57 bytes, 22 instructions)

```
mov [edx+8],ecx              ; reproduce the hooked instruction
push eax / push ebx
mov eax,[edx]                ; X bits
mov ecx,[edx+4]              ; Y bits
mov ebx, <TABLE_VA>
scan:  cmp [ebx],eax   / jne next / cmp [ebx+4],ecx / je found
next:  add ebx,0x10    / cmp ebx,<TABLE_END> / jb scan / jmp done
found: mov eax,[ebx+8]  -> [edx]        ; new X
       mov eax,[ebx+0xc]-> [edx+4]      ; new Y
done:  pop ebx / pop eax / mov ecx,eax  ; reproduce 0x6946F2
       jmp 0x6946F4
```

- Comparison is a plain **32-bit integer compare of the float bits** — exactly
  the bit-for-bit equality wanted, so no FPU is touched and there is no x87 state
  to preserve.
- **Stack discipline:** `EDX == ESP` on entry (from `mov edx,esp` at `0x6946E2`);
  the two pushes drop ESP to EDX−8 and both pops restore it, so the `call` runs
  with `ESP == EDX` exactly as originally. These are proper pushes, **not** the
  below-ESP scratch used by the older cave.
- Flags are clobbered but nothing consumes them before the `test eax,eax` that
  follows the call.
- **EDX/ESI/EDI/EBP/ESP are never written** — asserted programmatically by
  `verify_code()`, not just by inspection.

### The table

**16 bytes per entry: `oldX, oldY, newX, newY`, all float32.** Keyed on the
vanilla authored world position (all 340 are unique game-wide).

Current: **250 entries = 4,000 B at `0x86D010` .. `0x86DFB0`.**

### PE section space

The table outgrew the `.text` cave. Exact arithmetic: the tail runs
`0x73C263`..`0x73D000` = **3,485 B**; the patcher places the routine at
`CAVE_VA = 0x73C270` and the table at `(CAVE_VA + 0x80) & ~0xF` = `0x73C2F0`, so
the table's own space is `0x73C2F0`..`0x73D000` = **3,344 B = 209 entries max**.
(Older notes quote "~215", which is the looser `3485/16` estimate before the
code's 0x80 reservation.) Options considered:

| option | verdict |
|---|---|
| scavenge other `.rdata`/`.data` runs | rejected — ~113 entries total, split table complicates the routine, `.data` zeros are live globals |
| shrink the entry below 16 B | rejected — key needs 8 B and payload needs 8 B, both float32 |
| **add a 5th PE section** | **rejected** — its header would land at `0xAA8`..`0xACF` and destroy the `Hellspawn Reborn` watermark at `0xAC0` |
| **grow the last section (`.rsrc`)** | **chosen** |

`tools/pe_space.py` changes **three header fields and appends zeros**:

```
.rsrc VirtualSize    0x36BD8 -> 0x39000
.rsrc SizeOfRawData  0x37000 -> 0x39000
SizeOfImage          0x46D000 -> 0x46F000
+ 8192 zero bytes appended at EOF   (exactly where .rsrc's raw data already ended)
```

Region at VA `0x86D000`, opened with the magic **`K1MAPNTS`** so a re-run is
idempotent; the table area is `0x86D010`, **8,176 usable bytes = 511 entries** of
headroom. It is read-only initialised data, which is all a table needs — **the
match routine stays in the executable `.text` cave**, because this region is not
executable. Existing resource entries are untouched; this only adds unused space
after them.

Verified after write: section count unchanged, all three header fields, raw data
still ends at EOF, region reachable and marked, **watermark preserved**.

`note_table_patch.py` addresses the table through the section table
(`va_to_off` → `pe_space.rva_to_off`) — `va - IMAGE_BASE` is valid only for
`.text`. `check_target` verifies the two destinations separately now that they
live in different sections.

### Verification performed on every build

1. keystone-assembled instruction by instruction (no hand-encoded ModRM); only
   the four branch displacements computed by us.
2. capstone re-disassembled and checked against an expected mnemonic flow, that
   every branch resolves to the intended label, that the table base/end are the
   intended immediates, and that no instruction writes EDX/ESI/EDI/EBP/ESP.
3. Applied to a staging copy first, verified, then the live exe; both readbacks
   byte-exact.
4. **End-to-end simulation against the patched binary**: read the table back out
   of the exe as the CPU will see it and simulate the lookup for **all 340 notes**
   — every corrected note resolves to exactly its intended map pixel, 0
   expected-but-absent, **0 unintended matches** among the rest.

### The one real assumption

That `[esi]`/`[esi+4]` at this call site holds the note's **raw authored**
XPosition/YPosition, not a transformed or copied-and-adjusted value. Everything
else is proven. **If it were wrong the table would simply never match and no note
would move** — a silent failure, which is why the first in-game check was
`ebo_m12aa` "Engine Room" (32 px, unmistakable). It moved. Assumption holds.

### Degradation and compatibility

- **Touches no game data** — cannot conflict with any content mod.
- **Degrades gracefully:** keyed on the vanilla authored position, so if another
  mod repositions a note itself, the key stops matching and we leave it alone —
  their fix wins, no fight.
- Notes in mod-added areas are absent from the table and untouched.
- Shares ground only with other **exe** patchers (UniWS, k1hrm, 4 GB/no-CD).
  Apply ours **last** from a stock exe.
- **Resolution independence is structural**: the table stores world coordinates,
  upstream of the whole resolution chain, so one table is correct at every
  resolution. Changing resolution means re-running the *widescreen* patcher, as
  it already does; the note table is unaffected.

### A real bug this caught: `%.6f` is not enough precision

The patcher re-derives every table key from the **real module `.git`** and
cross-checks it against the CSV. That immediately failed on **17 of 172 keys**:
positions were written as `%.6f`, which is too coarse for small coordinates —
float32 spacing near 7.0 is ~5e-7, so `7.279155731201172` round-tripped to
`7.27915620803833`, one ULP out. **A one-ULP-wrong key never matches**, so those
17 notes would have silently gone uncorrected with nothing to indicate why.
`note_corrections.py` now writes `%.9g` (float32-exact).

> **Lesson: any float written to a file and later compared for bit equality needs
> `%.9g`/`%.17g`, never `%.Nf`.**
