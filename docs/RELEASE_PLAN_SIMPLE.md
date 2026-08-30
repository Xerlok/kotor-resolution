# RELEASE PLAN — the short, plain version

Updated 2026-08-30 after the scope decision. This is
[RELEASE_PLAN.md](RELEASE_PLAN.md) with the technical detail stripped out.

---

## What we are releasing

**"K1 Area Map Fixes"** — one mod, one patcher, released under GPLv3.

We ship **only the things we worked out ourselves**, all of which are about the
Area Map:

1. **The map fills its frame** instead of sitting small in the corner — and the
   little HUD minimap keeps working while it does, which is the part everyone
   else got stuck on.
2. **Map note markers land in the right place.**
3. **Your character and your party members land in the right place.**
4. **250 map notes moved to where they should have been.** The original game
   simply put them in the wrong spots.
5. **Bigger map icons** — later version.

## What we are *not* doing

Everything to do with widescreen itself: making the game accept your resolution,
fixing the menus, the fonts, the main menu, the dialogue black bars. **Other
mods already do all of that**, and the player installs them first:

> Editable Executable (Steam only) → UniWS → k1hrm → other mods → **ours**

We had written our own versions of the first two. They stay in the project as
tools we use for testing, but they are not part of the release.

The dialogue black bars turned out not to be ours at all — k1hrm's own patcher
asks about it and does it by default. Dropped from the plan.

## Why this scope is better

- **The licence problem is solved.** It only existed because of the widescreen
  code we were going to ship. We now release under GPLv3 and credit the k1hrm
  author, and that's the end of it. It had been blocking release since 28 August.
- **The patcher gets much smaller** and there is far less that can go wrong.
- **We can stop asking the user questions.** k1hrm writes your resolution into
  the game file. Our patcher can just *read* it. So it knows your resolution
  without asking, and if it isn't there, it knows k1hrm hasn't been run and can
  say so plainly. It can also check that the matching menu files were installed.
  This kills the single most common way people break this kind of mod — a
  mismatch between three places the resolution has to agree.

## The good news from the review

The k1hrm mod we now depend on ships ready-made layouts for **49 resolutions**,
including every one we care about — 1080p, 1440p, 4K, 16:10, ultrawide and
super-ultrawide. I checked our map maths against all 49 of them and **it lines up
at every single one.** That was the biggest unknown going in.

## The problems still on the list

1. **We have no backup of the project itself.** Thousands of lines of notes and
   tools, plus 32 MB of map drawings you made by hand that cannot be recreated,
   on one disk with no version history. Still the thing that worries me most.
2. **We've never actually tested with the real UniWS and k1hrm.** Everything so
   far was tested on a game patched by *our own* versions of those tools. The
   reasoning says it will work fine — but that's now the only path we support, so
   it has to be proven rather than assumed. This is the first real job.
3. **Map icons are still tiny** at high resolutions. Worst at 4K. Next version.
4. **On very wide screens the map gets stretched** — about 1.8× at 21:9, 2.7× at
   32:9. The markers still land correctly, it just looks odd. Worth looking at on
   a real ultrawide before deciding to do anything.
5. **We only have the Steam version to test with.** GOG and the old disc version
   should work, but we can't prove it, so we'll say "should work" and have the
   patcher refuse rather than risk damaging a file it doesn't recognise.

## What we'd test, and what we'd claim

**Properly tested (played in game):** 2560×1600, 1920×1080, 3440×1440, 3840×2160.

**Quick check:** 2560×1440, 1920×1200, 2560×1080, 5120×1440, plus 1600×1200 as a
sanity control.

**Everything else:** "supported, but not tested" — in those words.

For resolutions your monitor can't show, your graphics card can fake them
(Nvidia DSR / AMD VSR). Worth turning on first.

The checklist per resolution is now short, because menus and lists aren't ours
any more: does the map fill its frame, are the notes right, does the minimap
still work, do the markers follow you, does opening and closing the map
repeatedly stay stable.

A lot can also be checked **without running the game** — patch a copy at all 49
resolutions and verify the numbers automatically. That's what makes "tested" an
honest word.

## Which other mods to check against

UniWS and k1hrm are now **required**, not merely compatible. The Community Patch
is worth checking — and there's a neat trick: one of our existing tools can tell
us automatically whether it moves any map note, which beats reading a changelog.

One mod, **KotorUniResPatch**, does a similar job a different way. Those two can't
be used together and we should say so plainly.

Art and texture mods are no risk at all.

## How players install it

A small patcher with **Apply** and **Revert**, plus the source code alongside for
people who don't want to run a stranger's program. Same shape as other KOTOR exe
mods, including one released this June.

It should check what it's about to patch and stop politely if it doesn't
recognise it, keep a backup and a record of what it changed, and detect k1hrm
rather than trusting the user. Antivirus software may complain; we publish
checksums and explain why.

## Suggested order

0. **Back up the project** (git). Install two missing tools.
1. **Build and test the real chain** — official UniWS, official k1hrm, then ours.
   Prove it works before anything else.
2. Build the patcher.
3. Build the automatic tests.
4. Test the resolutions.
5. Test against other mods.
6. Package and release 1.0.
7. Version 1.1: bigger map icons.

## Still unanswered

**Does it work on GOG and the disc version?** Probably, but we have no copy to
try it on.
