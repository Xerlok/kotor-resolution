K1 Area Map Fixes
=================

For Star Wars: Knights of the Old Republic (the first one), on PC.

If you play KOTOR at a widescreen or high resolution, the map screen is a
mess. This fixes it:

  * the map fills the map screen instead of sitting small in one corner
  * the little map in the corner during play keeps working
  * your marker, your party and the map notes sit where they should
  * 250 map notes that were in the wrong place are moved to the right one

That last one is a BioWare bug, not a resolution bug - those notes have been
slightly off since 2003. They're fixed here too.


BEFORE YOU START
----------------
This mod does NOT change your resolution. It fixes the map after something
else has already made the game run at your resolution.

So you need three other things first, in this order. All free.

  1. KOTOR Editable Executable
     https://deadlystream.com/files/file/1320-kotor-editable-executable/

     Steam and GOG ship a swkotor.exe that's locked - no mod can edit it,
     including the two below. This is an unlocked copy you drop into your
     game folder. Everyone doing this kind of mod starts here.

  2. UniWS
     https://www.wsgf.org/article/universal-widescreen-uniws-patcher

     Makes the game offer your resolution. Pick "Star Wars: KOTOR" from the
     list, and when it asks which interface, choose 1024x768 - NOT 800x600.
     Picking the wrong one here is the most common mistake.

  3. KotOR High Resolution Menus (k1hrm), by ndix UR
     https://deadlystream.com/files/file/1159-kotor-high-resolution-menus/

     Redraws all the menus for your resolution. Run its patcher, then copy
     the menu files for your resolution into your game's Override folder.

Then this mod, last.

(If those links are dead by the time you read this, search DeadlyStream for
the mod names - they've all been up for years.)

Two optional mods, if you want them, go BETWEEN k1hrm and this one:
the K1 Ultrawide Letterbox Fix, and the 4 GB patch. Order matters. There's
a reason, and it's in "More info\COMPATIBILITY.txt".


INSTALLING
----------
Unzip this whole folder somewhere first. If you try to run it from inside the
zip, it stops and tells you to unzip it - Windows runs it from a temporary
folder it deletes later, and Uninstall.bat would go with it.

You don't need Python, or anything else installed. Everything this needs is in
the box.

Then double-click:

    Install.bat

That's it. It finds your game on its own and reads your resolution out of it -
it never asks you, so there's nothing to get wrong.

If it says it can't find your game, drag your KOTOR folder onto Install.bat
and let go. That's the folder with swkotor.exe in it.

Windows may say "Windows protected your PC" with a blue box. That happens to
every small mod tool - nobody pays for a code signature. Click "More info",
then "Run anyway". If you'd rather not, see "Running it without the exe" at
the bottom.


UNINSTALLING
------------
    Uninstall.bat

Puts your original swkotor.exe back, exactly as it was. UniWS and the menus
mod stay installed - your game still runs at your resolution, it just doesn't
have the map fixes any more.

Your original swkotor.exe is copied somewhere safe before anything is changed:

    %LOCALAPPDATA%\K1AreaMapFixes\backup

(Paste that into Explorer's address bar to see it.) It is kept out of this
folder and out of your game folder on purpose, so deleting the download can't
cost you your original game file. If you have deleted this folder and want to
uninstall, just download the mod again and run Uninstall.bat from the new copy -
it will find the backup.


AFTER INSTALLING
----------------
Load a save and look at two things before you settle in:

  * the map screen
  * the small map in the corner while you're walking around

If either looks wrong, run Uninstall.bat and you're back where you started.


IF SOMETHING GOES WRONG
-----------------------
"It says two other mods have to go first"
    Exactly that - UniWS and the high-res menus mod. See BEFORE YOU START.

"It says my menu files don't match"
    The menus mod was run at one resolution and its menu files were copied
    from another. Copy the right set into your Override folder.

"It can't find my game"
    Drag your KOTOR folder onto Install.bat.

"Steam deleted my patched game"
    Steam's "verify integrity of game files" replaces any exe it doesn't
    recognise. It'll do that to any exe mod. Keep a copy of your patched
    swkotor.exe somewhere outside the game folder.

"My antivirus doesn't like it"
    See "Running it without the exe" below.

Anything else, or a message not listed here: "More info\TROUBLESHOOTING.txt"
has the full list, including what every refusal message means.


RUNNING IT WITHOUT THE EXE
--------------------------
You don't have to trust our program. The whole thing is a Python script and
it's in the box:

    python "More info\source\install.py"

Same for uninstalling, with revert.py. That does exactly what Install.bat does.
This route is the only thing here that needs Python installed - Install.bat
doesn't.

"More info\SHA256SUMS.txt" lists a checksum for every file here, if you want
to check nothing changed in transit.


WHICH RESOLUTIONS THIS WORKS AT
-------------------------------
The maths is checked automatically against all 49 resolutions the high-res
menus mod supports, from 800x600 up to 15360x8640. Four of them have actually
been played:

    2560x1600   16:10
    1920x1080   16:9
    3840x2400   16:10
    1600x1200   4:3

Everything else should work and is checked, but nobody has looked at it on a
real screen. Ultrawide (21:9 and 32:9) is in that group - there was no
ultrawide monitor to test on. If you run one, we'd genuinely like to know how
it goes, either way.


ONE THING WE FIX THAT ISN'T OURS
--------------------------------
The high-res menus mod ships two copies of its patcher, and they don't agree.
The .exe one - the one its own instructions tell Windows users to run - leaves
the map pushed off to one side. At 1920x1080 it ends up 640 pixels right and
300 down, hanging off the screen.

That isn't this mod, and it happens whether or not you install this mod. But
it looks exactly like our bug, so we check for it and finish the job. If we
do, we say so during install, and Uninstall.bat undoes it along with
everything else.


CREDITS
-------
  ndix UR       KotOR High Resolution Menus, and the resolution work this is
                built on top of. Required, and not included here.
  wsgf.org      UniWS. Required, and not included here.
  LaneDibello   Kotor Patch Manager, whose address database was a useful
                cross-check while working this out.
  PyKotor       for reading the game's file formats.
  Everyone at DeadlyStream who documented this engine over the last decade.


LICENCE
-------
GPL version 3 or later. The full text is in "More info\LICENSE".

The resolution work this builds on is ndix UR's hires_patcher.pl, also GPLv3.
None of it is included here - you install it yourself, as step 3 above.
