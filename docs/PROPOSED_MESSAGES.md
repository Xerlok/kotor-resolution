# Patcher wording — proposed, approved and IMPLEMENTED 2026-08-30

**Status: all of this is in the shipped patcher.** Kept as the record of what
the wording is meant to do and why, so a later edit does not undo the reasoning
by accident. `patcher/selftest.py` asserts on several of these strings, so
changing one here means changing it there too.

The three rules it was written to:

1. **Say what happened, then what to do.** Never open with a hex address.
2. **No jargon in the default output.** No "constants", "VA", "cave", "hook",
   "operand", "byte-exact", "re-disassembles". Those move behind `--details`.
3. **Never blame the user.** Most refusals are "this isn't ready yet", not
   "you did it wrong".

Names below assume `Install.bat` / `Uninstall.bat`. If you keep `Apply.bat` /
`Revert.bat`, swap them throughout.

---

## 1. A normal successful install

### Now (60+ lines; this is the abridged version)

```
K1 Area Map Fixes 1.0.0
requires UniWS + KotOR High Resolution Menus (k1hrm), already installed
game folder: D:\Steam\steamapps\common\swkotor

-- checks --------------------------------------------------------------
  [x] swkotor.exe is the 4042752-byte Editable Executable
  [x] k1hrm patched this exe for 2560x1600 (read from the exe, not asked)
  [x] k1hrm's Area Map centring constants are already correct
  [x] Override/map.gui draws the map at (380, 393, 1760, 853) - the .gui set matches the exe
  [x] 250 reviewed map-note corrections, sha256 880a325d982d74df...

-- patching ------------------------------------------------------------
  area-map x float: private copy 1760.0000 at VA 0x78CC00 (1 operands repointed; shared original left at vanilla for the HUD minimap)
  area-map marker fix: private calibration object injected
    kx=4.000000 at VA 0x78CC08, ky=3.333333 at VA 0x78CC0C
    cave: 60 bytes at VA 0x73C1D0
    hook: VA 0x6946D3 redirected to the cave (other 3 callers of 0x578E00 - the HUD/menu path - untouched)
  ...
-- verifying what is actually on disk ----------------------------------
  [x] the 'Hellspawn Reborn' watermark at 0xAC0 is preserved
  [x] match routine re-disassembles correctly (22 instructions, branches resolve)
  ... 21 lines ...
```

### Proposed

```
K1 Area Map Fixes 1.0

Looking at your game...
  Found it:  D:\Steam\steamapps\common\swkotor
  Your game is set up to run at 2560x1600.
  UniWS and the high-res menus mod are both installed. Good.
  Your menu files match your resolution. Good.
  Nothing installed that clashes with this mod.

Making a backup...
  Your original game file is now saved here, and Uninstall.bat needs it:
  backup\swkotor.exe.original

Patching...
  - the map now fills the map screen instead of sitting in a corner
  - the small corner map still works
  - your marker, your party and the map notes land in the right spots
  - 250 map notes moved to where they should have been

Checking the patched file... all 21 checks passed.

Done. Load a save and take a look at two things before you play for long:
  the map screen, and the small map in the corner.

If anything looks wrong, run Uninstall.bat and you're back to how you were.
Keep this folder - Uninstall.bat needs the backup that's in it.
```

Notes:

- `--details` reproduces today's full engineer output, unchanged. Nothing is
  hidden, it just isn't the default. `Install.bat --details` works too.
- The `Hellspawn Reborn` line stays in `--details` only. In the default output
  it reads like a virus warning; it is actually a marker inside the Editable
  Executable, and checking it is a *good* thing we do.
- The "sha256 880a325d..." line goes. It means nothing to a player and the
  patcher already refuses a damaged table on its own.

---

## 2. Already installed

### Now
```
K1 Area Map Fixes is already installed on this exe. Nothing to do.
To reinstall, run Revert.bat first.
```
### Proposed
```
This mod is already installed. Nothing to do.

If you want to install it again, run Uninstall.bat first.
```

---

## 3. Refusals

All of these keep the existing frame — a banner, and the sentence
**"Your game has not been changed."** — but with `!!!!!!` swapped for a plain
rule, because rows of exclamation marks read as panic.

### 3a. k1hrm not installed — the most common one by far

**Now**
```
this exe still has the vanilla 640x480 canvas constants, which means KotOR
High Resolution Menus (k1hrm) has not been run on it.
Install order:
  1. UniWS  - unlocks the resolution
  2. KotOR High Resolution Menus (k1hrm) - rebuilds the menus at that resolution
  3. this patcher
Both are required; this mod fixes the Area Map on top of them and does not
replace either.
```
**Proposed**
```
Not ready yet - two other mods have to go first.

This mod only fixes the map. It doesn't change your resolution, and it
can't run until the mods that do are in place:

  1. UniWS                        makes the game offer your resolution
  2. KotOR High Resolution Menus  redraws the menus to fit it
     (k1hrm, by ndix UR)
  3. this mod

Your game still has the original 640x480 menu sizes, so step 2 hasn't
been done. Install those two, then run this again.

Your game has not been changed.
```

### 3b. Game not found

**Now**
```
could not find your KOTOR install.
Run the patcher again with the folder that holds swkotor.exe:
    Apply.bat "C:\Path\To\swkotor"
```
**Proposed**
```
I couldn't find your KOTOR folder.

Easiest fix: drag your KOTOR folder onto Install.bat and let go.
(The folder with swkotor.exe in it - usually something like
 C:\Program Files (x86)\Steam\steamapps\common\swkotor)

Your game has not been changed.
```
*Drag-and-drop already works — `Install.bat` passes the dropped path straight
through. It has just never been written down anywhere.*

### 3c. Wrong game version

**DONE 2026-09-01 — shipped wording superseded the "Now"/"Proposed" pair below.**
The GOG finding (`docs/REVERSE_ENGINEERING.md` — GOG retail v1.03 IS the
Editable Executable, byte-for-byte save for 16 bytes of unused header padding)
made the original "Proposed" text wrong: it told GOG owners to install the
Editable Executable, which they neither need nor should. `detect.py`'s
`check_build` refusal, `patcher/TROUBLESHOOTING.txt` and `patcher/README.txt`
now split Steam and GOG instead of grouping them. Kept below for the record.

**Now (original, pre-GOG-finding)**
```
swkotor.exe is 5619712 bytes; this patcher only knows the 4042752-byte
"Editable Executable" that UniWS and KotOR High Resolution Menus are made for.
If you are on the Steam release, swap in the Editable Executable first...
The GOG and 4-CD builds are untested and will be refused here rather than
guessed at.
```
**Proposed (original, pre-GOG-finding — DO NOT reintroduce, wrong about GOG)**
```
This isn't the version of the game this mod can patch.

The Steam and GOG releases ship a swkotor.exe that no mod can patch,
including UniWS and the high-res menus mod. Everyone gets around it the
same way: install the "KOTOR Editable Executable" first. It's on
DeadlyStream and it's the standard first step for this kind of mod.

Once that's in, install UniWS and the high-res menus mod, then run this.

Your game has not been changed.
```
**Shipped instead** (`patcher/k1amf/detect.py:check_build`):
```
This isn't the version of the game this mod can patch.

If you're on Steam: Steam ships a swkotor.exe that no mod can patch - not
this one, not UniWS, not the high-res menus mod. Install the "KOTOR
Editable Executable" first. It's a free download on DeadlyStream and it's
the normal first step for this kind of mod. Then run UniWS and the
high-res menus mod, then this.

If you're on GOG: your own swkotor.exe should already work directly. This
usually means a different patch/language build, or the old 4-CD retail
disc, which this patcher doesn't recognise.

(Your swkotor.exe is %d bytes; the one I'm expecting is %d.)
```

### 3d. Menu files don't match the resolution

**Now**
```
Override/map.gui draws the map at (380, 393, 1760, 853), which is not what a
1920x1080 exe expects ((285, 265, 1320, 576)).
```
**Proposed**
```
Your menu files and your game don't match.

Your game is set up for 1920x1080, but the menu files in your Override
folder were made for a different resolution.

This usually means the high-res menus mod was run at one resolution and
the menu files were copied from another. Copy the menu file set that
matches 1920x1080 into your Override folder and run this again.

Your game has not been changed.
```

### 3e. Half-installed, or something else edited the file

Three separate refusals today (canvas constants disagree / implausible
resolution / centring constants unrecognised). They have the same cause and the
same fix, so I'd like them to read consistently:

**Proposed**
```
Something has already changed the part of the game this mod patches, and
I don't recognise what it did.

I'm not going to guess and risk breaking your game. The safe fix is to
start clean:

  1. put back an unmodified swkotor.exe (or reinstall the Editable
     Executable)
  2. run UniWS, then the high-res menus mod
  3. run this again

Your game has not been changed.
```
*(The exact values still print, one line, under it — they're what a bug report
needs. I'd keep that.)*

### 3f. Half-applied by us

**Now**
```
a previous run was interrupted, or something else has edited these bytes.
Run Revert.bat, or restore a clean exe...
Patching on top of a half-applied exe would corrupt it.
```
**Proposed**
```
A previous install didn't finish.

Run Uninstall.bat to put your backup back, then try again. If that
doesn't work, restore an unmodified swkotor.exe and redo UniWS and the
high-res menus mod.

I won't patch on top of a half-finished install - that would break the
game for real.

Your game has not been changed.
```

### 3g. Damaged download

**Now**
```
the map-note table in this patcher does not match its own checksum - the
download is damaged. Re-download rather than patching with it.
```
**Proposed**
```
This download is damaged.

The map data that came with the patcher doesn't match its own checksum,
so something went wrong downloading or unzipping it. Download it again.

Your game has not been changed.
```

### 3h. KPM warning (not a refusal — it continues)

**Now**
```
  [!] Kotor Patch Manager looks installed (KotorPatcher.dll, patch_config.toml).
      If its KotorUniResPatch is enabled, it re-scales the Area Map that
      this mod already scales, so the map will be wrong with both live.
      They cannot be fixed by ordering - turn that one patch off in KPM.
      Everything else in KPM is unaffected. Patching anyway.
```
**Proposed**
```
  Heads up: Kotor Patch Manager is installed here.
    If you have its "KotorUniResPatch" switched on, turn it off. It fixes
    the same map this mod does, and with both on the map comes out wrong.
    Nothing else in Kotor Patch Manager is affected.
    Carrying on with the install.
```

---

## 4. Verification failed after writing

The rarest and scariest message. It has to be calm and give one clear action.

**Now**
```
verification failed. Your original exe is at
    <path>
Restore it before running the game, and please report the failing line above.
```
**Proposed**
```
Something went wrong and I'm not confident the patch is correct.

Don't start the game yet. Run Uninstall.bat - it puts your original file
back. Nothing is lost.

Then please report this, and include the line above that has an empty
[ ] next to it, plus installed.json from this folder. That tells us
exactly what happened.
```

---

## 5. Uninstall

**Now**
```
K1 Area Map Fixes - revert
restored D:\...\swkotor.exe (2560x1600, as it was before this mod)
UniWS and KotOR High Resolution Menus are still installed; only this mod's
changes were undone.
```
**Proposed**
```
K1 Area Map Fixes - uninstall

Put your original game file back.

UniWS and the high-res menus mod are untouched - your game still runs at
2560x1600, it just doesn't have the map fixes any more.
```

### 5a. Nothing to uninstall
**Now**
```
no record of an install (installed.json is missing), so there is nothing to
revert.
If you moved or re-downloaded the patcher folder, use the backup you kept
instead.
```
**Proposed**
```
I can't find a record of this mod being installed, so there's nothing to
undo.

If you re-downloaded or moved this folder, the record of your install went
with the old one. Use the backup copy of swkotor.exe you kept, if you have
one.

Your game has not been changed.
```

### 5b. Someone else changed the file since

**Now**
```
swkotor.exe is not the file this patcher wrote - something has changed it since
(another mod, k1hrm re-run, or Steam's file verification).
Restoring the backup would throw those changes away.
Run  Revert.bat --force  if that is what you want.
```
**Proposed**
```
Your swkotor.exe isn't the one this mod created - something changed it
afterwards. Another mod, or Steam repairing the game, most likely.

If I put the old backup back now, whatever that other thing did gets
thrown away.

If you're happy to lose it, run:   Uninstall.bat --force

Your game has not been changed.
```

---

## 6. Two small things worth deciding

- **`Install.bat --details`** — the flag name. Alternatives: `--verbose`,
  `--technical`, `--full`. I'd use `--details`.
- **Writing a log file.** Every run could drop `last-run-log.txt` next to the
  bat with the full `--details` output, whether or not it was asked for. It
  costs nothing, and it turns "please re-run with --details and paste it" into
  "attach that file". My recommendation: yes.

## 7. UX feedback from the clean-install test, 2026-09-01 — NOT YET ACTIONED

Raised by the user while testing; explicitly deferred, not analyzed or
implemented yet. Record only.

- **`Uninstall.bat` gives no feedback while it's running** — during the wait at
  the start, nothing on screen says an uninstall is in progress.
- **`Uninstall.bat` doesn't clearly say it's done** when it finishes — no
  obvious "the mod is uninstalled" moment.
- **`Install.bat`'s finished state needs to be more visible** too — make it
  clearer/more prominent when installation has completed successfully.
