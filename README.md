# K1 Area Map Fixes

KOTOR 1's map screen was built for 4:3. Run the game at anything wider or taller and the Area Map sits small in one corner instead of filling the screen. Separately, 250 of the game's map notes have been in slightly the wrong spot since 2003, a BioWare positioning bug that has nothing to do with resolution. This patches both, on top of the usual widescreen mod stack.

It's a binary patcher, not a script or a data override: it edits `swkotor.exe` directly, the same way the mods it depends on do, and re-reads every byte it writes from disk to verify it before calling the job done.

## Features

- The in-game Area Map (the full-screen menu) fills its box instead of sitting in a corner
- The HUD minimap (the small map in the corner while you play) keeps working: easy to break by accident while fixing the Area Map, see *How It Works*
- Player marker, party markers, and map-note markers land where they belong
- 250 map notes get their stored positions corrected: a longstanding BioWare bug, unrelated to resolution
- Note and marker icons scale up at higher resolutions so they stay visible

## Requirements

- Star Wars: Knights of the Old Republic, PC, v1.03
  - **Steam** needs the "KOTOR Editable Executable" first (search DeadlyStream for it). Steam's own `swkotor.exe` is packed and can't be patched by anything, including UniWS and the mods below.
  - **GOG** needs nothing extra. GOG's own `swkotor.exe` (v1.03) is byte-for-byte the same file the Editable Executable unlocks: the only difference is 16 bytes of unused PE header padding.
  - 4-CD retail and no-CD-patched builds are untested. The patcher refuses anything that isn't exactly 4,042,752 bytes rather than guess.
- [UniWS](https://www.wsgf.org/article/universal-widescreen-uniws-patcher): unlocks the resolution
- [KotOR High Resolution Menus](https://deadlystream.com/files/file/1159-kotor-high-resolution-menus/) (k1hrm) by ndix UR: rebuilds the menu GUI files for your resolution
- Python 3.8+ only if you want to run from source instead of the packaged exe (`pip install capstone keystone-engine`)

Resolution support: confirmed in-game at 2560x1600, 1920x1080, 3840x2400, and 1600x1200. The scaling math is checked offline against all 49 resolution sets k1hrm ships, from 800x600 to 15360x8640, and should hold at any of them; the rest just haven't been run on real hardware, ultrawide (21:9, 32:9) included.

## Installation

1. Install the prerequisites above, in order: Editable Executable (Steam only) → UniWS → k1hrm, at the resolution you want to play at.
2. Unzip this mod to a real folder, not inside the zip, not in a temp folder.
3. Run `Install.bat`. It finds your game and reads your resolution out of the exe; it never asks you anything.
4. `Uninstall.bat` puts your original exe back.

No Python required: the packaged installer is a frozen executable. The Python source ships alongside it if you'd rather run that instead: `python source/install.py`.

Full instructions, troubleshooting, and a byte-level writeup of everything the patcher touches ship inside the release itself (`README.txt`, `TROUBLESHOOTING.txt`, `TECHNICAL.txt`).

## Compatibility

**Works with:**
- Kotor 1 Community Patch (K1CP) 1.10.0 (checked by measurement): of 4,064 waypoints K1CP moves or leaves alone game-wide, it touches 35, none of them map notes.
- K1 Ultrawide Letterbox Fix and the 4GB/LAA patch, both optional. Install them *before* this mod; their patcher gates on an exact file size, and this is the mod that grows the exe.
- 3440x1440 Enhanced HUD/UI and Menus (replaces k1hrm's own 3440x1440 set rather than stacking with it)
- Override art/texture mods with no overlapping ground: HD UI Menu Pack, Pretty Good! Icons, HD portraits, and similar.

**Doesn't work with:**
- Kotor Patch Manager's `KotorUniResPatch` specifically: it hooks the same Area Map draw function and rescales using the same shared constants, so with both active the map gets scaled twice. KPM itself is fine; that one patch inside it isn't. The installer detects KPM's presence and warns.
- Flawless Widescreen: process injection, nothing on disk to detect, not supported. WSGF's own guidance points KOTOR 1 users at UniWS + k1hrm anyway.

## How It Works

The accepted input is the Editable Executable after UniWS and k1hrm have both already run (4,042,752 bytes). The patcher:

1. Fixes k1hrm's Area Map centring constants if its Windows `.exe` patcher left them vanilla. It's a real bug in k1hrm's compiled build (the `.pl` script it ships doesn't have it), and left alone it puts the map `(width-640)/2, (height-480)/2` pixels off its box.
2. Rewrites 16 scale constants in the Area Map's draw path for your resolution. Two constants it deliberately *doesn't* touch are shared with the HUD minimap's own draw code: writing them in place turns the minimap black, found out the hard way, twice. Instead, scaled copies go into unused space and only the Area Map's own instructions get redirected to read them.
3. Scales marker icon sizes (notes, player arrow, party) above a threshold that leaves everything at 2560x1600 and below byte-for-byte untouched.
4. Patches three small calibration routines into spare code space for the note/player/party marker position math.
5. Grows the `.rsrc` section by 8 KB and writes a table of 250 corrected note positions plus a small match routine, hooked into the note-loading path. Notes are keyed by their stored world position rather than by module or index, so the table keeps working under mods that edit module files; verified against K1CP specifically.

Every write is re-read from disk afterward and checked: 21 checks in total, including one that nothing outside the documented byte ranges changed. A failed check means the run refuses to report success and points at the backup instead.

Exact offsets, the VA/file-offset conventions, and what each one does are documented in `TECHNICAL.txt`.

## Building

```
python tools/build_release.py
```

Freezes `install.py`/`revert.py` with PyInstaller (`--onedir`, deliberately: a self-extracting `--onefile` build stacks a second antivirus heuristic on top of the one already inherent to growing a PE section), assembles the release folder and zip, and hashes everything into `SHA256SUMS.txt`.

Needs `pyinstaller`, `capstone`, and `keystone-engine`.

## Development / Testing

```
python patcher/selftest.py
```
The fast one. Patches a test exe built from the official UniWS+k1hrm chain and checks the result against the in-game-confirmed md5 (`435108fdb65bac2151ab694e7fb8e36a`), plus the refusal and revert edge cases. Run this while changing anything under `patcher/`.

```
python tools/qa.py
```
The slow one. Sweeps all 49 of k1hrm's resolution sets and checks the map-scale math and note table at every one. Takes 15-20 minutes; run it before a release, not on every change.

```
python tools/verify_release.py
```
Runs against the actual built release artifact, not the source: applies and reverts end-to-end against a throwaway game folder, checks backup handling, and confirms the install works with no Python on `PATH` at all.

`downloads/`, `backups/`, and `staging/` are gitignored. You'll need your own copies of UniWS, k1hrm, and a legally-owned copy of the game to build test fixtures locally.

## Known Issues

- **The HUD minimap is a fixed 120x120 pixel box at every resolution.** k1hrm never scales it (it's the one part of the HUD it deliberately leaves alone), and this mod doesn't enlarge it either yet. Its on-screen size turns out to be tied to exe-side draw code that shares constants with the Area Map, not just a GUI rectangle, so it's more than a one-line fix. Planned for a future release.
- Player/party marker positions have a sub-2px rounding imprecision. Vanilla has this too; not introduced or worsened here.
- Ultrawide resolutions (21:9, 32:9) are verified in the scaling math but not confirmed on real ultrawide hardware.
- 4-CD retail and no-CD-patched builds are unverified: not known broken, just untested, and the patcher refuses to guess rather than risk it.

## License

GPLv3 or later. See `LICENSE`.

Built on top of ndix UR's `hires_patcher.pl` (also GPLv3), none of that code is redistributed here; it's a separate required download, see Requirements.

## Credits

- **ndix UR**: KotOR High Resolution Menus, and the resolution work this project builds on
- **wsgf.org**: UniWS
- **LaneDibello**: Kotor Patch Manager, whose address database was a useful cross-check while reverse-engineering this
- **PyKotor**: file format reference
- Everyone at DeadlyStream who's documented this engine over the last two decades
