# KPM address database (imported reference, 2026-08-28)

`kotor1_0_3.db` is the symbol database from **LaneDibello/Kotor-Patch-Manager**
(`AddressDatabases/kotor1_0_3.db`, MIT — see `LICENSE.kpm`). Imported as a
read-only reference; nothing in this project depends on it at runtime.

## Why it is trustworthy here

It is keyed to **our exact executable**. Verified 2026-08-28:

- `downloads/swkotor.exe` (our editable exe) sha256 `761f9466f456a839…c49e9886`
  = KPM's `kotor1_cdcrack_103`, byte-identical.
- `backups/swkotor.exe.steam-backup` sha256 `34e6d971…39f34c88`
  = KPM's `kotor1_steam_103`, byte-identical.
- The research agent verified 36 of 36 of KPM's K1 hook `original_bytes` against
  our editable exe at the stated VAs.

Contents: 9,711 functions, 977 classes, 4,727 class member offsets, 21 globals.

## It confirms our hand-derived model, name for name

| our finding | DB says |
|---|---|
| 0x578E00 map transform | `CSWSAreaMap::GetMapPixelFromWorldCoord` (EXACT) |
| 0x578F10 grid pixel | `CSWSAreaMap::GetGridPixelFromMapPixel` (EXACT) |
| 0x5791B0 party marker position read | `CSWSAreaMap::GetPartyMemberMapLocation` (EXACT) |
| 0x6943D0 Area Map draw | `CSWGuiMapHider::Draw` (EXACT) |
| 0x693F60 icon material ctor | `CSWGuiMapHider::Constructor` (EXACT) |
| our hooks 0x6946D3 / 0x6946EF | inside `CSWGuiMapHider::Draw` — as we concluded |
| 0x4B4960 "false-positive prologue" | `CServerExoAppInternal::ResolvePlayerByFirstName` — a **different** function from `UpdateMapData` (0x4B4E80), which is exactly the trap NOTES.md documents |

## New leads it hands us (not yet acted on)

- **`CSWSAreaMap::SetPartyMemberWorldLocation` (0x5790C0)** — the *writer* of the
  cached party/player map position whose reader (0x5791B0) we already found. Open
  item 2 (marker double-rounding) belongs at the writer, not the reader.
- **`CSWSAreaMap::GetMapRotateCCWFromWorldOrientation` (0x578ED0)** — the
  NorthAxis rotation we derived by hand.
- **`CSWGuiMapHider::HitCheckMouse` (0x693300)** — note click hit-testing.
- `CSWGuiMapHider::InitializeMapNotes` (0x692C70), `ClearMapNotes` (0x692E30),
  `GetNextMapNote` (0x692E80), `GetPrevMapNote` (0x693090), `SetMapNote`
  (0x6932A0) — the whole map-note lifecycle, named.
- **`CServerExoAppInternal::UpdateMapData` (0x4B4E80)** — where KotorUniResPatch
  hooks to guarantee scaled constants are in place *before the first marker plot
  fills the cache*.
- Globals: `SCREEN_WIDTH` 0x78D1D4, `SCREEN_HEIGHT` 0x78D1D8.

## Query it like this

```python
import sqlite3
c = sqlite3.connect("reference/kpm/kotor1_0_3.db")
# what function contains this address?
c.execute("select address,class_name,function_name from functions "
          "where address<=? order by address desc limit 1", (0x6946EF,)).fetchone()
# every function of a class
c.execute("select address,function_name from functions where class_name=? order by address",
          ("CSWSAreaMap",)).fetchall()
```

Tables: `functions(class_name, function_name, address, notes, calling_convention,
param_size_bytes)`, `offsets(class_name, member_name, offset, notes)`,
`classes`, `global_pointers`, `game_version`.

**Caveat:** these are third-party symbol names, not ground truth. They have
matched everything we independently derived so far, but a name is a claim —
verify by disassembly before relying on one for a patch.
