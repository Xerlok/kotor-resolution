K1 Area Map Fixes
=================

Fixes the Star Wars: Knights of the Old Republic Area Map at high resolutions:

  * the map fills its box instead of sitting small in the corner
  * the HUD minimap keeps working (this is why the fix is not a one-line edit)
  * player, party and map-note markers land where they actually are
  * 250 map notes whose stored positions were wrong are corrected

WHAT YOU NEED FIRST
-------------------
This mod does NOT set your resolution and does not include anything that does.
Install these two first, in this order, at the resolution you want to play at:

  1. UniWS  - unlocks widescreen resolutions in the engine
  2. KotOR High Resolution Menus (k1hrm) by ndix UR - rebuilds the menus and
     GUI files for that resolution

Then run this patcher. It reads the resolution out of your exe - it never asks
you - and refuses to run if either prerequisite is missing or if your Override
.gui files are from a different resolution than your exe.

INSTALL
-------
  Apply.bat

If your game is not found automatically, pass the folder that holds
swkotor.exe:

  Apply.bat "D:\SteamLibrary\steamapps\common\swkotor"

UNINSTALL
---------
  Revert.bat

Your original exe is kept in this folder (backup\swkotor.exe.original) along
with a record of exactly what was changed (installed.json). Revert restores
that exe and leaves UniWS and k1hrm in place. Keep this folder if you want to
be able to uninstall.

AFTER INSTALLING
----------------
Load a save and check BOTH the Area Map (the map screen) and the HUD minimap
before settling in for a long session.

CHANGING RESOLUTION LATER
-------------------------
Revert this mod first, then re-run UniWS and k1hrm from a clean Editable
Executable for the new resolution, then run this patcher again. It gates on the
untouched original values by design, so it will refuse rather than stack a
second set of changes on top of the first.

LICENCE
-------
GPLv3 or later - see LICENSE. The byte-level resolution work this builds on is
ndix UR's (hires_patcher.pl, GPLv3); no part of it is bundled here.
