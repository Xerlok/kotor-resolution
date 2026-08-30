# DATA FORMATS — what we learned about KOTOR's file formats

Everything here was verified against the real game files, not taken on trust from
a wiki. Where a community source disagreed with our data, our data won and the
disagreement is recorded.

## KEY / BIF

`chitin.key` is the resource index; `data/*.bif` are the archives.
`tools/keybif.py` reads both — confirmed against BioWare's official Key/BIF spec
and verified live (lists all `.gui` resources in `gui.bif`, extracts any by name).

`extract_resource(bif_path, resource_index)` takes an **index into that BIF's own
Variable Resource Table** (the "y" from a KeyEntry), and **returns a tuple** —
`(data, ...)` — not raw bytes. Easy to get wrong.

**`models.bif` is 954 MB.** `keybif.extract_resource` slurps the whole file and
is unusable for it. `map_geometry.GameResources` is a **seeking** KEY/BIF reader
built for exactly this: it caches the resource table and seeks to the entry.

## GFF (V3.2) — `.gui`, `.are`, `.git`, `.ifo`, `.utp`, `.utc`, …

`tools/gff.py` (reader) and `tools/gff_writer.py` (writer). Confirmed against the
official GFF spec, plus **three KOTOR/Odyssey-specific field types the base
Aurora spec doesn't document** (cross-checked against the community Perl
implementation `KotOR-Bioware-Libs/GFF.pm`):

| type | meaning |
|---|---|
| 16 | `ORIENTATION` — 4 floats |
| 17 | `VECTOR` — 3 floats (used for both position vectors and RGB colour) |
| 18 | `STRREF` — a `dialog.tlk` string reference |

**`kotor-modding.fandom.com/GFF_Format` has 16/17 swapped** (it lists
16=Position/12 bytes, 17=Rotation/16 bytes). Checked empirically rather than
trusting either source: in `m13aa.git`'s `CameraList`, fields labelled `Position`
decode as type **17** into sane world XYZ, and fields labelled `Orientation`
decode as type **16** into genuine unit quaternions (norm 1.0 across all 31
cameras). **Our code is correct for KOTOR's actual files. Do not "fix" this.**

### Writer round-trip behaviour — two different answers, both true

- `roundtrip_test.py`: parsing `mainmenu.gui` and writing it back is
  **byte-for-byte identical**.
- But `map.gui` is **not**: 1,557 of 7,347 bytes differ after a no-op
  parse→write, purely field/label **ordering**.

So the writer is trustworthy but **not byte-stable for every file**. When you
must prove a write is safe, compare **semantically**: parse both and diff the
flattened field tree. For `map.gui` that gave 291 fields with 0 differences.

## `.are` — the `Map` struct

The struct has **11 fields**, not the 4 originally modelled:

```
MapResX, NorthAxis, MapZoom          (sint32)
WorldPt1X, WorldPt1Y, WorldPt2X, WorldPt2Y   (float, raw world coords)
MapPt1X,  MapPt1Y,  MapPt2X,  MapPt2Y        (float, normalised 0..1)
```

Real values for `m13aa`: `MapPt1={0.3659, 0.3630}`, `MapPt2={0.5545, 0.9630}`,
`WorldPt1={101.3, 36.2}`, `WorldPt2={237.2, 109.9}`.

`MapResX`/`NorthAxis`/`MapZoom` being **sint32** (not float) is independently
confirmed by `KOTORCommunityPatches/KOTOR_GFF_Templates`
(`K1/Modules/danm13/m13aa.are.xml`), which also reproduced our own RIM/GFF
extraction byte-for-byte.

How the loader consumes them: see
[REVERSE_ENGINEERING](REVERSE_ENGINEERING.md#are-loader).
How the calibration is derived: see [ARCHITECTURE §2](ARCHITECTURE.md).

**`MapZoom` is present in every `Map` struct with value 1 everywhere checked.
It is NOT read by `0x578E00`. UNKNOWN whether anything else reads it, and
whether it ever differs.** Low priority — no observed effect.

**Community documentation for this struct does not exist.** A sweep of 17 KOTOR
modding-community links (DeadlyStream tutorial series + hub, 4 archived
LucasForums threads, 6 more tutorials, czerka-rd.fandom.com's format pages, plus
`kotor-modding.fandom.com/GFF_Format` and the GFF Templates repo) produced a
**clean, consistent negative result**: nothing anywhere covers the `.ARE` `Map`
struct's calibration semantics or how the toolset's Area Properties dialog sets
them. **Our reverse-engineering is the most complete account of this struct's
behaviour that exists anywhere findable.**

## `.git` — map notes and everything positioned

Map notes are entries in `WaypointList` with `TemplateResRef = sw_mapnote001`,
carrying `HasMapNote` / `MapNoteEnabled` / `MapNote` (a CExoLocString → strref)
plus plain `XPosition`/`YPosition`/`ZPosition` floats.

**`HasMapNote` is what makes a note render**, not `MapNoteEnabled`. See
[ARCHITECTURE §6](ARCHITECTURE.md#6-map-notes-as-data).

### A bug worth remembering: not every list uses the same field names

`map_calibration.POSITIONED_LISTS` originally read every list with
`XPosition`/`YPosition` — but **doors store `X`/`Y`**. Every door in the game was
silently missing from the object lists, and `dist_to_object` never saw one.
Fixed with per-list field names; the survey's p90 moved 9.2 → 8.5 px as a result.

**Transitions:** doors and triggers carry `TransitionDestin` (a **strref**, i.e.
the destination's own dialog.tlk name) alongside `LinkedToModule`/`LinkedTo`.
Trigger anchors must use the centroid of the trigger's `Geometry` polygon — its
points are **local to the trigger position**, not world-space.

**Object display names:** a `.git` entry has only a TemplateResRef; the readable
name is `LocName` in the template (`.utp`/`.utc`/… in the module's `_s.rim`, else
`data/templates.bif`).

## `.lyt` / `.wok` — room geometry

- `<areaResRef>.lyt` in `data/layouts.bif` lists an area's rooms.
- Each room's walkmesh is `<roomModel>.wok` in `data/models.bif` (1202 of them).
- **`.wok` vertices are ALREADY WORLD-SPACE — do NOT add the `.lyt` room offset**
  (nor the `.wok` header `position`). Doing so throws rooms hundreds of map
  pixels off. Verified on `m12aa`.
- **Empty `.wok`s exist** (exterior hull shells, no walkable faces at all) and
  must be skipped — they are not places.

`tools/map_geometry.py` wraps this: `Room.contains / distance /
nearest_floor_point / centroid_on_floor`, `AreaGeometry.room_at / nearest_room /
on_floor`. `centroid_on_floor()` exists because a ring-shaped room's centroid can
land in the hole (the Ebon Hawk's main hold is one).

## TPC — textures

Header (128 bytes): `uint32 dataSize`, `float alphaBlending`, `uint16 width`,
`uint16 height`, `uint8 encoding`, `uint8 mipmapCount`, then reserved.

- `dataSize > 0` → **compressed**: encoding 2 = DXT1, encoding 4 = DXT5.
- `dataSize == 0` → **uncompressed**: encoding 1 = 8-bit grey, 2 = RGB, 4 = RGBA.
- **Data is stored bottom-up — flip vertically before sampling.**

PyKotor has a working TPC reader (`pykotor.resource.formats.tpc`: `TPC`,
`read_tpc`, `TPCBinaryReader`, `TPCDDSReader/Writer`, `TPCTGAReader/Writer`,
`TPCBMPWriter`, `tpc_auto`/`convert`) and `map_calibration.load_map_texture` uses
it, handling the flip and the 440-crop.

### PyKotor API actually used (verified end-to-end against the real install)

```python
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.formats.erf import ERF, ERFType, write_erf, read_erf
from pykotor.resource.type import ResourceType
# GFF struct access:  .acquire(label, default) to read
#                     .set_single(label, value) to write
#                     .at(index) for list entries
```

Verified 2026-08-25, not merely imported: `read_rim()` on the live
`ebo_m12aa.rim` found all 3 resources and the "Engine" waypoint's exact known
values; `read_gff`/`write_gff` round-tripped a modified `YPosition`
(11.764173731201172 → 11.76417350769043 — that ~1e-7 delta is float32 write/read
rounding, not a bug); `ERF`/`write_erf`/`read_erf` built a real `.mod`, wrote it,
read it back, and the corrected value survived the full pack/unpack round trip.
Installed as `pykotor` 2.3.12 (pulls `bioware-kaitai-formats`, `kaitaistruct`,
`ply`).

Real example: `Override/lbl_map.tpc` is **2048×2048, DXT1, 12 mipmaps**,
2,796,344 bytes, first mip 2,097,152 B — a k1hrm/HD replacement of the Area Map
panel background.

**Useful trick if we ever edit a DXT1 texture in place:** a DXT1 block whose two
colour endpoints are **equal** decodes to a solid colour, so blocks can be
rewritten as flat colour without implementing a real encoder.

**TXI fields** worth knowing if an Override HD texture ever looks unexpectedly
downsampled: `downsamplemin`/`downsamplemax`, `compresstexture`,
`maxSizeHQ/LQ`, `minSizeHQ/LQ`.

## ERF / RIM / MOD

**KOTOR 1 uses ERF version `V1.0` exclusively** — confirmed by xoreos's
`erffile.h` ("1.0: Used in Neverwinter Nights, Knights of the Old Republic I and
II, Jade Empire and The Witcher — 16 ASCII characters per resource name") and by
xoreos-tools' packer, which only emits V1.0 for these games. **V1.1 (32-char
resref) is NWN2-only and will NOT load correctly in KOTOR** — this is the "wrong
version silently fails" trap.

**Header — 160 bytes**, offsets from file start, little-endian:

| field | offset | size | type |
|---|---|---|---|
| FileType | 0x00 | 4 | `"MOD "` for .mod (`"ERF "`/`"SAV "`/`"HAK "` otherwise) |
| Version | 0x04 | 4 | `"V1.0"` |
| LanguageCount | 0x08 | 4 | uint32 |
| LocalizedStringSize | 0x0C | 4 | uint32 (bytes) |
| EntryCount | 0x10 | 4 | uint32 |
| OffsetToLocalizedString | 0x14 | 4 | = 160 (fixed) |
| OffsetToKeyList | 0x18 | 4 | = 160 + LocalizedStringSize |
| OffsetToResourceList | 0x1C | 4 | = OffsetToKeyList + EntryCount×24 |
| BuildYear | 0x20 | 4 | uint32, since 1900 |
| BuildDay | 0x24 | 4 | uint32, day-of-year, 0-indexed |
| DescriptionStrRef | 0x28 | 4 | uint32 |
| Reserved | 0x2C | 116 | zero-filled |

**Key List entry — 24 bytes** each, immediately after the localized string table:
ResRef `char[16]` ASCII lowercase, no null terminator (0x00) + ResID uint32
(0x10, just the entry's own index) + ResType uint16 (0x14) + Unused uint16 zero
(0x16).

**Resource List entry — 8 bytes** each, immediately after the key list:
OffsetToResource uint32 + ResourceSize uint32. Resource data follows packed
contiguously, offsets computed cumulatively — **no padding or alignment between
entries**.

Localized-string LanguageID formula: `2*language_id + gender`.

Primary sources: `Bioware_Aurora_ERF_Format.pdf` (nwn.wiki), xoreos
`src/aurora/erffile.{h,cpp}`, xoreos-tools `src/aurora/erfwriter.cpp` /
`src/erf.cpp`.

**RIM** format (our hand-rolled reader): 120-byte header, 32-byte resource
entries. Confirmed correct because the decoded resrefs/restypes came out sane
(`m13aa`/2012 = ARE, `m13aa`/2023 = GIT, `module`/2014 = IFO).

### KOTOR-specific `.mod` practice (researched, not assumed)

- **Load priority: `Override/` > `.mod` in `Modules/` > that module's
  `.rim`/`_s.rim` pair.** A `.mod` **fully supersedes** the RIM pair for that
  module — it does not layer.
- **A `.mod` must contain every resource from BOTH the `.rim` and `_s.rim`.**
  Confirmed, not inferred: a partial `.mod` silently drops anything it doesn't
  include (one modder traced a module load hang to a forgotten `.are`).
- **`.git` files are not supported in `Override/`** — and a loose one is actively
  dangerous if it *is* read: the engine stores per-object local variables from
  `.git` data inside saves, so a loose Override `.git` can desync from what a save
  has baked in. Our own Phase 1a test confirmed the mechanism first-hand.
- **Precedent for exactly our technique:** a DeadlyStream tutorial ("About Map
  Notes") walks through editing a module's `.git` `WaypointList` via K-GFF —
  clone a waypoint struct, set `HasMapNote`/`MapNoteEnabled`=1, set
  `XPosition`/`YPosition`/`ZPosition` — to *add* a note. Field-for-field the same
  operation as *moving* one.
- **UNKNOWN:** whether the `.git`'s `GameVersion` field matters to the engine
  (vs just to editor tooling). Safest practice: source the base `.git` from a real
  K1 extraction, so whatever it says is already correct.
- Tool cautions: KOTOR Tool's "extract for module editing" is unreliable for a
  full `.mod` rebuild (use "extract entire RIM file" on both RIMs);
  ErfEdit-built `.mod`s reportedly crash for at least one user.

## Save games

`SAVEGAME.sav` is an **ERF** containing one `<module>.sav` per visited module;
each holds `<area>.git` + `<area>.are` + `Module.ifo`. See
[ARCHITECTURE §7](ARCHITECTURE.md#7-save-game-caching-decides-delivery-mechanism)
for the caching semantics — including that the cached copy is keyed by **area**
resref and its `WaypointList` ordering differs from the module's own file.

## `.gui`

`.gui` files are GFF. The control tree is `TGuiPanel` → `CONTROLS` list, each with
`TAG`, `CONTROLTYPE`, `EXTENT` (`LEFT`/`TOP`/`WIDTH`/`HEIGHT`), `BORDER`
(`EDGE`/`CORNER`/`FILL`/`DIMENSION`/`INNEROFFSET`), `COLOR`, and possibly nested
`CONTROLS`.

`map.gui`'s controls at 2560×1600 (our Override copy):

```
TGuiPanel      (0,0,2560,1600)     BORDER fill='lbl_map'
  LBL_Map      (380,393,1760,853)  BORDER fill=''      <- the map viewport
  LBL_MapNote  (360,1253,1840,110)
  LBL_Area     (260,290,2040,70)
  LBL_COMPASS  (2162,377,213,213)  BORDER fill='lbl_mapnorth'
  BTN_UP       (287,1273,67,67)    BTN_DOWN (2211,1273,67,67)
  BTN_PRTYSLCT (452,1367,1112,43)  BTN_RETURN (452,1417,1112,43)
  BTN_EXIT     (1572,1367,584,93)
```

Vanilla: panel 640×480, `LBL_Map` **(95, 118, 440, 256)** — the viewport is
**1:1 with the 440×256 map-pixel space**. Ours is exactly that scaled by
(4.0, 3.3333).

**`LBL_Map`'s `BORDER.FILL` is empty in both vanilla and Override.** The map
texture is bound by engine code from the area resref — this was a red herring
that cost a session.

The panel's own `BORDER.FILL = 'lbl_map'` is the full-screen background art, and
**that art contains the 1-px frame line** drawn around the map opening. See
[failures F18](EXPERIMENTS_AND_FAILED_APPROACHES.md#f18).

The HUD minimap's box, `LBL_MAP` in `mipc*.gui`, is a **fixed 512×512 in every
one of the four vanilla resolution buckets** — it was never meant to scale, and
k1hrm correctly left it alone. "Very small on a 2560×1600 screen" is expected
vanilla behaviour, not a bug.
