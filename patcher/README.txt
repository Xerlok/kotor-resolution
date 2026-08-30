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

ONE THING WE FIX THAT IS NOT OURS
---------------------------------
k1hrm ships two copies of its patcher: hires_patcher.pl (a Perl script) and
hires_patcher.exe (a compiled build of it). They do not agree. The .exe - the
one hires_patcher.bat runs, and the one k1hrm's own guide tells Windows users
to use - leaves four values inside the Area Map code at their vanilla 640x480,
where the .pl correctly writes your resolution. The two outputs differ by
exactly 6 bytes.

Those four values are what centre the Area Map on its frame. Left vanilla, the
map is drawn (your_width - 640) / 2 pixels to the right and
(your_height - 480) / 2 pixels down from where it belongs, so at 1920x1080 it
sits 640 across and 300 down and runs off the screen. It looks exactly like a
bug in this mod. It is not, and it happens with or without this mod installed.

So this patcher checks those four values and finishes the job if k1hrm's .exe
did not. It will only do that when they hold exactly the vanilla 640x480 AND
your exe already proves k1hrm ran; anything else it refuses rather than guess.
It is recorded in installed.json like every other change, and Revert.bat undoes
it - which puts you back to the broken k1hrm state, not a fixed one.

If you would rather k1hrm did its own job, run its .pl instead of its .exe:

  perl hires_patcher.pl WIDTH HEIGHT no swkotor.exe

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
