# REVERSE-ENGINEERING REFERENCE — addresses, offsets, constants, structures

All addresses are **virtual addresses (VA)** unless stated. For this binary
`VA = 0x400000 + file_offset` for `.text`/`.rdata`/`.data`, because
`PointerToRawData == VirtualAddress` for those sections. **That identity does
NOT hold for `.rsrc`** (raw 0x3A4000 vs RVA 0x436000) — anything addressing the
new table region must go through the section table
(`pe_space.rva_to_off`). This bit us once.

Target binary: the UniWS-patched **"KOTOR Editable Executable"** (FairLight
pre-Steam-DRM v1.03), sha256 `761f9466f456a839…c49e9886`. The packed Steam exe
(`.bind` section, `.text` entropy 8.00) cannot be statically patched at all.

## Cross-check: the KPM symbol database

`reference/kpm/kotor1_0_3.db` (MIT, from LaneDibello/Kotor-Patch-Manager) is
keyed to **our exact executable** — 9,711 functions, 977 classes, 4,727 member
offsets, 21 globals. It confirms every function boundary we derived by hand,
name for name. Query it:

```python
import sqlite3
c = sqlite3.connect("reference/kpm/kotor1_0_3.db")
c.execute("select address,class_name,function_name from functions "
          "where address<=? order by address desc limit 1", (0x6946EF,)).fetchone()
```

## Functions

### Map coordinate core (`CSWSAreaMap`)

| VA | name | notes |
|---|---|---|
| `0x578C60` | Map calibration **constructor** | 12 args. **Exactly ONE caller in the whole exe**: the ARE loader at `0x509F68`. Only runs on a fresh area load |
| `0x578E00` | **`GetMapPixelFromWorldCoord`** — the world→map-pixel transform | `ret 0x14`; takes 5 stack dwords: a Vector3 (0xC) **plus two separate output pointers**, X written via `mov [edi],eax` at `0x578E7A`, Y via `mov [edx],eax` at `0x578E91` |
| `0x578ED0` | `GetMapRotateCCWFromWorldOrientation` | the NorthAxis rotation, named by the KPM DB |
| `0x578F10` | `GetGridPixelFromMapPixel` | |
| `0x5790C0` | **`SetPartyMemberWorldLocation`** | the **writer** of the cached party/player map position; stores to `[esi + i*4 + 0x28]` |
| `0x5791B0` | **`GetPartyMemberMapLocation`** | the **reader**; pure cache read, never calls `0x578E00` |
| `0x5792D0` | player-position helper | 1 unconditional call from the dispatcher |
| `0x579090` | grid getter | reads `[obj+4]`, `[obj+8]`, `[obj+0xc]`, returns `[obj]`. This is the HUD's only tie to the calibration object |

Inside `0x578E00`:

| VA | instruction | meaning |
|---|---|---|
| `0x578E64` | `fdiv dword ptr [esi+0x18]` | X scale |
| `0x578E7F` | `fdiv dword ptr [esi+0x1c]` | Y scale |
| `0x578E9B` | `cmp ecx, 0x6e0` (imm here) | X bound — **patched to 1760** |
| `0x578EA6` | `cmp eax, 0x355` (imm here) | Y bound — **patched to 853** |

**The four callers of `0x578E00`** (found by brute-force `E8`+rel32 scan, immune
to disassembly drift): `0x579104`, `0x57924B`, `0x579313` (all inside the generic
marker-setter cluster) and **`0x6946F4`** (the Area Map's own site).

### Area Map GUI (`CSWGuiMapHider` / `CSWGuiInGameMap`)

| VA | name | notes |
|---|---|---|
| `0x6943D0` | **`CSWGuiMapHider::Draw`** | the Area Map draw. `sub esp, 0x1dc` prologue. Virtual method, vtable entry at `0x754770` |
| `0x693F60` | `CSWGuiMapHider::Constructor` | creates the marker **materials** (icon sizes live here) |
| `0x693300` | `CSWGuiMapHider::HitCheckMouse` | note click hit-testing |
| `0x692C70` | `InitializeMapNotes` | |
| `0x692E30` | `ClearMapNotes` | |
| `0x692E80` / `0x693090` | `GetNextMapNote` / `GetPrevMapNote` | |
| `0x6932A0` | `SetMapNote` | |
| `0x693650` | `CSWGuiInGameMap::OnPanelAdded` | loads the area texture and attaches it to `LBL_Map` |
| `0x694D50` | `map.gui` init | binds `LBL_Map`, `LBL_MapNote`, `LBL_Area`, `LBL_COMPASS`, `BTN_RETURN`, `BTN_PRTYSLCT`, `BTN_EXIT`, `BTN_UP`, `BTN_DOWN`. **This is how the exe finds the box at runtime — nothing hardcodes its size** |

### Inside `0x6943D0` — the note loop and the hook window

```
0x694458-0x694612  grid/tile-size setup (uses the private 0x78CC00/04 constants)
0x694671...        per-note linked-list walk:
                     0x5E9B60 get-node -> 0x4AE750 lookup-by-key
                     -> two calls through vtable+0x58 (validity, then fetch)
                     -> esi = note object;  0x694689: add esi, 0x90
                   loop tail 0x6949C1 (inc edi) -> 0x6949C2 (0x5E9B90 get-next)
0x6946B7  mov ecx, [0x7a39fc]      ; object chain begins
0x6946BD  mov dword [esp+0x10], 0  ; pre-zeroes the outY slot
0x6946C5  mov ecx, [ecx+8]
0x6946C8  call 0x4AE6B0
0x6946CD  mov eax, [eax+0x218]
0x6946D3  <-- MARKER-FIX HOOK (5 B), resumes 0x6946D8
0x6946D8  lea ecx,[esp+0x24] ; push ecx   (the X output pointer)
0x6946DD  mov ecx,[esi]      ; note world X
0x6946DF  sub esp, 0xc
0x6946E2  mov edx, esp
0x6946E4  mov [edx],ecx      ; -> [esp+0]
0x6946E6  mov ecx,[esi+4]    ; note world Y
0x6946E9  mov [edx+4],ecx    ; -> [esp+4]
0x6946EC  mov ecx,[esi+8]    ; note world Z
0x6946EF  mov [edx+8],ecx    | exactly 5 bytes: 89 4a 08 8b c8
0x6946F2  mov ecx,eax        | <-- NOTE-TABLE HOOK (5 B)
0x6946F4  call 0x578E00      ; resume here
0x694701  <- transform returned: X in [esp+0x20], Y in [esp+0x10]
0x694701  cmp edx,[ebx+0x23c]  ; "is this the selected note"
0x69470D / 0x694711            ; icon rect reads [esp+0x20] / [esp+0x10]
```

**Important corrections that were made and re-made here:**
- The world-position input Vector3 is at `[esp+0]/[esp+4]/[esp+8]` **relative to
  the esp right after `sub esp,0xc` at `0x6946DF`** — *not* `[esp+0x10]/[esp+0x14]`,
  which is a different reference frame (the transform's *output* slots).
- At both `0x6946F4` and `0x694701`, **`ESI` already equals `note_ptr + 0x90`**
  because `add esi,0x90` ran at `0x694689`. The position floats are at plain
  `ESI` (offset 0), not `esi+0x90`. A capture of `esi+0x90` is `note_ptr+0x120`
  and means nothing — this mistake was made once and the all-zero dump nearly
  became a false conclusion.
- `ESI` is unchanged across the `0x578E00` call (callee-saved).

### HUD minimap

| VA | notes |
|---|---|
| `0x688100` | the real HUD minimap draw. Body ends `ret 4` at `0x6883B9`. Own `fdivr [0x747748]` at `0x688153` |
| `0x6880C0` | a small unrelated 64-byte function — **older notes called this "HUD map drawing"; that address was imprecise** |
| `0x68BF50` | HUD class init; binds `mipc28x6` / `mipc216x12` / `mipc210x7` — this is how `0x688100` was identified |
| `0x68B089` | call site of the HUD draw |
| `0x68ABF8` | minimap reads the real texture size; bytes `8B 96 00 5E 00 00` |

### Generic dispatch chain (the trap)

| VA | name / role |
|---|---|
| `0x4BABB0` | generic per-screen update. **Zero static references anywhere in the file** — both a brute-force `E8` scan and a whole-file 4-byte absolute-value scan found 0, so it is reached only through a runtime-computed function pointer. Calls `0x4B4E80` at `0x4BAC51` |
| `0x4B4E80` | `CServerExoAppInternal::UpdateMapData`. Early-out `test esi/eax; je 0x4b4f40` around `0x4B4EA1`–`0x4B4EAB` is an **existence** check, not a panel-type discriminator |
| `0x4B14F0` | generic memoised single-item lookup (key at `this+0x1b918`, result at `+0x1b91c`, via `0x4D8230` keyed by `this+0x10060` against a list at `this+0x1005c`, virtual call through vtable+0x20 on a miss). **Not** panel-discriminating |
| `0x5ED8B0` | trivial two-hop getter, `return ((this+4)->+0x270)`. One of a neighbourhood of identical 16-byte-aligned thunks (`0x5ED8C0`, `0x5ED8D0`, `0x5ED910`, …). **Not** panel-discriminating |
| `0x4B4960` | **`CServerExoAppInternal::ResolvePlayerByFirstName`** — the documented false-positive "nearest prologue". A *different* function from `0x4B4E80` |

### ARE loader

| VA | role |
|---|---|
| `0x509C50`–`0x50A050` | the Map-struct loader (disassembled in full). The nearest-prologue heuristic answered `0x508C50`/`0x508C40` — **another false positive**; the true start was never pinned down but does not block anything |
| `0x509D1B`, `0x509D58`, `0x509D97`, `0x509DD6` | the four `fmul` instructions (MapPt × 440.0/256.0) |
| `0x509D1D`, `0x509D5A`, `0x509D99`, `0x509DD8` | their disp32 operands (what the reverted redirect rewrote) |
| `0x509F01`–`0x509F5E` | the argument push sequence |
| `0x509F68` | the single `call 0x578C60` |

Loader behaviour, CONFIRMED by disassembly:
- **`MapResX` gates everything**: if absent/zero it jumps to a branch that
  constructs the Map object with all-zero defaults (`push 0` ×11, `push 0x58`,
  `push 1`) — areas without map data get a null object.
- Reads `NorthAxis`, `MapZoom` via the generic int getter `0x411C90`.
- Checks `MapPt1X`'s GFF **type code** (`call 0x411880; cmp eax, 8`; 8 = FLOAT)
  to choose a float path vs a fallback (`jne 0x509DF7`) — presumably for
  older/rare non-float data.
- Float path: re-reads all four `MapPt` via the float getter `0x411D00`, and for
  each: `fmul` 440.0/256.0, `fadd` the rounding-bias constant `0x73E9AC`, then
  `0x6FC750`/`0x6FAE8C` to round to int.
- **Then unconditionally** reads `WorldPt1X/Y`, `WorldPt2X/Y` via the same float
  getter and stores each straight from the FPU (`fstp`) with **no `fmul`, no
  rounding**.

### Helpers

`0x411C90` int getter · `0x411880` type getter · `0x411D00` float getter ·
`0x6FC750`/`0x6FAE8C` FPU round-to-int · `0x6FA7E6` alloc wrapper ·
`0x6FD8CF` the CRT allocator (hooked in the Unicorn harness at this exact depth
so `0x6FA7E6`'s own stack cleanup still runs) · `0x4AE6B0`, `0x4AE750`,
`0x5E9B60` (get-node), `0x5E9B90` (get-next), `0x4D8230` ·
`0x406D80`, `0x405ED0`, `0x415000`, `0x417050` (tooltip text construction).

## Globals and constants

| VA | value / role |
|---|---|
| `0x7A39FC` | root of the global chain both marker paths resolve through |
| `0x78D1D4` / `0x78D1D8` | `SCREEN_WIDTH` / `SCREEN_HEIGHT` |
| `0x73E9AC` | `0.5` — the rounding bias |
| `0x740CBC` | `-1.0` |
| `0x747748` | **`440.0`** — shared, read by ARE loader, `0x578F10`-family, HUD `0x688100`, Area Map `0x6943D0`. Left **vanilla** by us |
| `0x7455D4` | **`256.0`** — same, left vanilla |
| `0x78CC00` / `0x78CC04` | our **private** copies: `1760.0` / `853.333` |
| `0x78CC08` / `0x78CC0C` | our `kx` / `ky`: `4.0` / `3.3333332538604736` |
| `0x7A23B4..BC`, `0x7A23C0..C8` | tooltip/label 3D-anchor defaults written into the note struct at `+0x90`/`+0x104` around `0x694924`–`0x694967`. **Investigated and confirmed a dead end** — the whole block is gated by "is this the selected note" and builds the tooltip's text object, not the marker position |

### Marker icon immediates (all still **vanilla** in our exe)

| VA | instruction | meaning |
|---|---|---|
| `0x694718` | `add eax, -0xa` | selected note: X −= 10 |
| `0x69471F` | `mov eax, 0x14` | selected note: 20×20 |
| `0x694762` | `mov eax, 0xe` | unselected note: 14×14 (with −7/−7) |
| — | `-0x10` / 32 | player arrow |
| — | `-8` / 16 | party circle |

And the **material creation** sizes in the `CSWGuiMapHider` constructor
(`0x693F60`), which must also be scaled or the draw rect just stretches a small
texture:

| VA | value | icon |
|---|---|---|
| `0x69405B` | `0x20` | player arrow |
| `0x6940DC` | `0x10` | party circle |
| `0x69418F` | `0x14` | target / note marker |

Measured on the 2560×1600 screenshot: selected icon 18×18 px, unselected 12×12 —
identical to vanilla. A 14 px icon was **5.5 %** of the map's height in vanilla
and is **1.6 %** at our resolution.

## The calibration object (per area, one singleton)

| offset | field |
|---|---|
| `+0x00` | grid array pointer |
| `+0x04` | grid count |
| `+0x08` | grid X dimension (clamped, max 88) |
| `+0x0C` | grid Y dimension (a rounded int) |
| `+0x10` | **NorthAxis** |
| `+0x14` | a float |
| `+0x18` / `+0x1C` | **X / Y scale** |
| `+0x20` / `+0x24` | **X / Y offset** |

Object size copied by the notes cave: **0x28 bytes** (covers every field
`0x578E00` reads). A live-captured example (Ebon Hawk, patched):
scaleX `0.076325`, scaleY `-0.096452`, offsetX `-16.7252`, offsetY `85.7785`
— vanilla `0.30529803` / `-0.32150539` / `-16.725168` / `85.778497` divided by
`kx`/`ky`, reproducing the live object **to the last float32 bit**
(`-0.09645162522792816`). Using *unrounded* `MapPt_scaled` does **not** match, so
the rounding step in the model is real and correctly identified.

## PE layout

| section | VA | vsize | raw ptr | raw size |
|---|---|---|---|---|
| `.text` | `0x401000` | 3,391,488 | `0x1000` | 3,391,488 |
| `.rdata` | `0x73D000` | 326,654 | `0x33D000` | 327,680 |
| `.data` | `0x78D000` | 689,304 | `0x38D000` | 94,208 |
| `.rsrc` | `0x836000` | 224,216 → **0x39000** | `0x3A4000` | 229,376 → **0x39000** |

`SizeOfImage` `0x46D000` → **`0x46F000`**. `SectionAlignment` = `FileAlignment`
= `0x1000`. `SizeOfHeaders` `0x1000`. Section headers end at file offset
**`0xAA8`**; a 5th header would occupy `0xAA8`..`0xACF`.

### Free space in `.text` — measured, not estimated

- **`0x73C263` .. `0x73D000` = 3,485 bytes.** This is the **only** zero run
  ≥ 600 B anywhere in `.text` (numpy scan of the pre-note-table backup).
- `.text` ends exactly at `0x73D000` where `.rdata` begins, so it cannot be
  extended.
- Other measured runs, too small and/or awkward: `.rdata` **1008 B at
  `0x78CC10`**, **265 B at `0x75E631`**. About 113 more entries even if both were
  used, and a split table complicates the match routine.
- **`.data` is out.** Its file-zero bytes are *not* runtime-free — the game
  writes real globals there, proven by `0x7A39FC` (part of the shared global
  chain) sitting inside that exact byte range.

### The `Hellspawn Reborn` watermark

16 bytes at file offset **`0xAC0`**. **Absent from the pristine Steam exe** and
written by none of our tools — it is a third-party patcher's marker (UniWS).
Because section headers must be a contiguous array, adding a 5th section header
would overwrite it. That is why we grew `.rsrc` instead. It is preserved and
verified after every `pe_space.py apply`.

## <a id="patcher-offset-tables-file-offsets-from-hires_patchpy"></a>Patcher offset tables (FILE offsets, from `hires_patch.py`)

```
negative_offsets_x = [0xB6C7, 0xBA6C, 0xB537, 0xB8DC, 0xB7B7, 0xBB5C]
negative_offsets_y = [0xB6DA, 0xBA83, 0xB54A, 0xB8F3, 0xB7CA, 0xBB73]
```

These are **pairs per exe build**: the first of each pair fixes clicking menu
**buttons**, the second fixes clicking **list items** (save games, inventory,
journal…). Our port originally flattened the pairs and kept only the first —
that single data-entry bug *was* the list-click bug.

```
map_offsets_x            = 0x179009, 0x179344, 0x179377, 0x17937E,
                           0x178E9B, 0x178F15, 0x295082
map_offsets_y            = 0x17901A, 0x179358, 0x179383, 0x17938A,
                           0x178EA6, 0x178F24, 0x295064, 0x29508A
map_projection_offsets_x = 0x29505C
map_grid                 = 0x17906F      (never matches; correctly left unpatched)
map_offsets_float_x / _y = 0x347748 / 0x3455D4   (VA 0x747748 / 0x7455D4)
BIGMAP_FLOAT_OPERANDS    = {"x": [0x2944AA], "y": [0x2944C6]}   (VA 0x6944A8 / 0x6944C4)
PRIVATE_FLOAT_SLOTS      = {"x": 0x38CC00, ...}                 (VA 0x78CC00)
MARKER_KX_SLOT / KY_SLOT = 0x38CC08 / 0x38CC0C                  (VA 0x78CC08 / 0x78CC0C)
```

**`0x178E9B`/`0x178EA6` are VAs `0x578E9B`/`0x578EA6`** — the bound-check
immediates *inside* `0x578E00`. So `mapscale` widened the check from
"reject outside 440×256" to "reject outside 1760×853" for **all four callers**,
including the generic HUD path, which still produces vanilla-space (0..440)
coordinates. Positions vanilla rejected are now accepted there. **Untested side
effect, no observed symptom.** Also note these are patched as **int16**, so a
target width above ~11,900 px would silently corrupt the operand (not reachable
by any real resolution: 2560×1600→1760/853, 3840×2160→2640/1152).

## UniWS gate sites

`0x68C4E3` / `0x68C4F3` / `0x68C4FA` — our exe holds `0` / `0` / `2560`. The
patch signature from `patches.ini` is `3D20030000EFEFEFEFEFEF58020000`, matching
exactly one location, the `cmp eax,800 / cmp [esp+8],600` structure.

Undocumented UniWS behaviour found by byte-diffing our own port: the "kept"
interface-preset bucket slot is rewritten to the **actual target width** (2560),
not left at its own literal default — `patches.ini`'s "no setx" means "use the
real width".

## Secondary addresses, historical corrections, and one-off observations

Kept because each cost real effort to obtain and none is re-derivable cheaply.

### Historical misattributions — do not re-adopt

| address | what it was claimed to be | what it actually is |
|---|---|---|
| **`0x694A39` / `0x694AAC`** | "the Area Map's own calibration getter call sites" (asserted repeatedly, 9 mentions in the log) | they call **`0x5791B0`**, the party-member position getter — no relation to the `obj+0x18..0x24` calibration fields. The misattribution happened because both loops bound-check against 3 |
| `0x694822` | a function start | a coincidentally-matching prologue **inside** `0x6943D0`. Its apparent "callers" `0x6935FD`, `0x694BB1`, `0x694C8B`, `0x694D3D` are just later code in the same method |
| `0x695000` | "the call site we'd been poking at" | inside `0x694D50`, i.e. `map.gui`'s init — which is how that function was identified |
| `0x6880C0` | "HUD map drawing" | a small unrelated 64-byte function; the real one is `0x688100` |

### Cave internals (needed if the notes cave is ever extended)

The notes cave `0x73C1D0`..`0x73C207` ends with
`pop esi` (**`0x73C1FF`**), `pop edi` (**`0x73C200`**), `pop ebx` (**`0x73C201`**),
then the reproduced hook bytes, then `jmp 0x6946D8`.

**The only point where ESI (world-position pointer, restored) and EBX (the
private calibration object) are BOTH simultaneously valid is *inside* the cave,
between `pop esi` and `pop ebx`.** An earlier plan said to reuse them "at the
resume site" — wrong: by then EBX holds the caller's original value and only EAX
carries the private object (until `0x6946F2` copies it to ECX).

Live-captured: the private copy sat at **`ECX = ESP-0x3F0`**, matching the
documented "borrowed stack scratch near `esp-0x400`" design.

### Superseded table layouts (the same routine, different data)

| build | table span | entries |
|---|---|---|
| first Phase 3 | `0x73C2F0` .. `0x73CDB0` | 172 |
| line-centring | `0x73C2F0` .. `0x73CD80` | 169 |
| atlas pilot / pre-atlas | ends `0x73CDE0` | 175 |
| **current** | **`0x86D010` .. `0x86DFB0`** | **250** |

`0x73C2F0` is the value `tools/state.py` used to hardcode, which made it report
"0 entries / MISMATCH" against a perfectly good patch once the table moved.

### Other one-offs

| address | meaning |
|---|---|
| `0x578F3E` | a third reference to the 440.0 constant (a shared map-coordinate helper), found when sanity-checking `disasm_helpers.py` |
| `0x509F60` | start of the ARE loader's constructor-call setup (the `call` itself is `0x509F68`) |
| `0x579318` | the return address that identified the marker-setter cluster as `0x578E00`'s caller during the live session |
| `0x579210` | gates the Area Map's note-handling block |
| `0x6883B5` / `0x6883B9` | the old "not yet fully mapped ~0x6883B5+" marker turned out to be `0x688100`'s **epilogue**; the body ends `ret 4` at `0x6883B9` |
| `0x347558`–`0x347790` | the compiled-in literal label table of GFF field-name strings, used with the generic getter mechanism. This is what `refs` was run against to find the ARE loader |
| `0x747730` / `0x747738` / `0x747740` / `0x74774C` | the field-name string VAs for `MapPt2Y`/`MapPt2X`/`MapPt1Y`/`MapPt1X`, referenced right beside the loader's reads — how the loader was identified |
| `0x754710` | a literal string address used in the tooltip-text block |
| `0x44200000` | IEEE754 for `640.0` — searched for when hunting a float-shaped version of the canvas constant |
| `0x4B1580` | a second, unrelated call site of `0x4B14F0` (evidence it is a generic helper) |
| `0x4B4EA1` / `0x4B4EA9` | the `test esi,esi` / `test eax,eax` early-out pair in `0x4B4E80` — an **existence** check, not a panel discriminator |
| `0x4B4EF3` / `0x4B4F10` | the two call sites from `0x4B4E80` into the marker-setter cluster; both land cleanly with no intervening `ret` |
| `0x4BAC51` | the single call from `0x4BABB0` to `0x4B4E80` |
| `0x10040`–`0x10050`, `0x10078` | fixed child-widget slots and the visibility flag bits `0x4BABB0` updates off `this` |
| `0x23CC` | `[esi + edi*8*3 + 0x23cc]`-style per-entity array addressing seen inside `0x6943D0` |
| `0x694755`–`0x6948B2`, `0x694907`–`0x694967`, `0x694988` | the selected-note tooltip block (dead end, F14) |
| `0x694A00` | reads the party count byte (default 3 if null) for the party loop |
| `0x6945A0`, `0x6946F9`, `0x6947D2`, `0x69475A` | anchors used when re-disassembling the draw function from a verified-good address |
| `~0xB6C0`, `~0xBA60`, `~0xAA60` | the approximate offsets k1hrm's README uses to name its three hex edits (gog build); the exact ones are in the offset tables above |

## Prior art: J0-o/KotorUniResPatch (addresses verified against OUR exe)

A runtime DLL for Kotor Patch Manager. **Licence: none (all rights reserved) —
the addresses are facts about the binary and ours to use; their C++ source text
is not.** Their model: one **integer** scale, `max(1, (screenHeight + 300) / 600)`
= **3** at 1600p, applied to both minimap and area map "so shared map coordinates
remain consistent".

| what they write | our exe already holds |
|---|---|
| `440*scale` at `0x578E9B`, `0x578F15`, `0x579009`, `0x579344`, `0x579377`, `0x57937E` | **1760** — we already scale these |
| `256*scale` at `0x578EA6`, `0x578F24`, `0x57901A`, `0x579358`, `0x579383`, `0x57938A` | **853** — we already scale these |
| `0x69505C`/`0x695064`/`0x695082`/`0x69508A` (engine dims 512/256/440/256) | **2048 / 853 / 1760 / 853** — already scaled |
| icon material sizes `0x69405B`/`0x6940DC`/`0x69418F` | **still vanilla `0x20`/`0x10`/`0x14`** — we do NOT do this |
| floats `0x747748` / `0x7455D4` = `440*scale` / `256*scale` | **still vanilla 440.0 / 256.0** — we do NOT do this |

**That float asymmetry is a real open lead**: every integer twin is scaled to
1760/853 while the floats stay vanilla, so some path computes in vanilla float
space. In their code these floats feed the fog/grid overlay (`FUN_00688100`),
which they must temporarily restore to vanilla for that one draw. Candidate
explanation for residual cosmetic oddities — **not investigated by us**.

Two ideas worth stealing (mechanism, not code):
1. **Scale the marker rect generically** instead of patching each immediate:
   hook the draw sites (`0x69473A`, `0x6949A7`, `0x694A6B`, `0x694AD7`), reject
   rects wider/taller than 64 px, multiply w/h by scale, then
   `left -= (newW-oldW)/2`, `top -= (newH-oldH)/2` — i.e. **derive** the centring
   our `-0xa`/`-0x10`/`-8` immediates hardcode. One routine covers all four icons.
2. **Compute in scaled space, never rescale afterwards.** They patch the bound
   constants *inside* the transform so the engine's own conversion happens once
   in scaled space — no `k*round(...)` step. Their hook at `0x4B4E80` exists only
   to guarantee the constants are in place *before the first marker plot fills
   the cache*. That independently confirms our per-frame cache finding and gives
   the right fix for our double-rounding.

Their `CSWGuiMapHider` clip: `mapHider` at **obj+0xE38**, `mapTexture` at
**obj+0x1080**. Setting the hider to `(0,0,viewportW,viewportH)` and the texture
rect to the full `512×256*scale` means the unused 72 columns and any overrun are
**clipped, not drawn**.

Bonus KPM patch, verified applicable: `hud-minimap-map-size-fix-v1` makes the
HUD minimap treat any atlas as logically 512×256 by replacing
`0x68ABF8: 8B 96 00 5E 00 00` with
`C7 44 24 30 00 02 00 00 / C7 44 24 34 00 01 00 00 / 8B 96 00 5E 00 00`.
Only needed if we ever ship HD map art.

**Conflicts:** no byte overlap with our hooks (ours are `0x6946D3+5` and
`0x6946EF+5`; their lowest in that function is `0x69473A+9`) and no cave overlap
(KPM `VirtualAlloc`s at runtime). But **functionally they are alternatives, not
additions** — our icon immediates would feed already-adjusted rects into their
rect scaler and double-scale.

**Unverified:** the enclosing instruction at each `0x578Exx`/`0x5793xx`/`0x69505x`
site was not disassembled — only the operand value was read. Confirm instruction
boundaries before writing any of them.
