# DISTRIBUTION — how 1.0 reaches normal users

Written 2026-08-30 as analysis only. **Updated 2026-08-31: the three proposed
changes are implemented and Q1 is answered.** **Updated 2026-09-01: Q2's GOG
half is answered by measurement — the prerequisite is Steam-only now.** Q2's
Steam-only legal/naming half and Q3 (the "I couldn't find your KOTOR folder"
prompt) are still open.

The question put to the debate: *single installer/exe, or multiple visible
files?* Two agents argued opposing sides from the actual repo; this is the
resolved outcome plus the open questions the user raised afterwards.

---

## The framing was already obsolete

`dist/K1-Area-Map-Fixes-1.0.0/` is **not** "many loose files". It is a hybrid:
two frozen exes behind `Install.bat` / `Uninstall.bat`, with source, LICENSE and
per-file hashes in `More info/`. 44 files, 32 MB expanded, 12 MB zipped.

So the live question was only: *do we wrap that in an Inno/NSIS `setup.exe`?*

## Decision: no installer. Ship the archive that already exists.

Reasons, in the order they actually carry weight:

1. **AV heuristics stack, and one is already spent.** `pe_space.py` grows a PE
   section — a known trigger we cannot avoid. `tools/build_release.py:10` already
   records the deliberate choice of `--onedir` over `--onefile` because
   self-extraction is a second trigger. Adding a wrapper exe spends a third to
   save one double-click, for an audience already told to download an "Editable
   Executable" from a forum.
2. **SmartScreen inverts the "one dialog" argument.** An unsigned `setup.exe`
   from a zero-reputation publisher draws a harder block than a `.bat` does, and
   it is the one artifact a cautious user cannot inspect. Three mild warnings
   beat one hard one.
3. **Scannability.** Nexus quarantines nested/opaque archives specifically
   because contents cannot be scanned. Loose files scan clean.
4. **GPLv3 means source ships regardless**, so the archive is multi-file anyway;
   a wrapper adds only opacity, and buries the
   `python "More info\source\install.py"` escape hatch that README and
   TROUBLESHOOTING both point AV-worried users at.
5. **Community norm.** `SHIPPING.md:35-50` — four precedents (k1hrm included) all
   shaped exactly like the current release.
6. **No second toolchain**, and no second acceptance surface that
   `verify_release.py` does not cover.

### What the pro-installer side got right

One hit landed, and it is a genuine defect: **`manifest._home()`
(`patcher/k1amf/manifest.py:19-50`) anchors `installed.json` and `backup\` on the
folder containing `Install.bat`.** The user's only copy of their pre-patch
`swkotor.exe` therefore lives in their Downloads folder, and the README has to
tell them to keep it forever. Running from inside the zip is already a documented
beginner-killer (`STATE.md:71`, `TROUBLESHOOTING.txt`).

**This is a correctness bug, not a packaging one, and the installer was the wrong
cure** — a sealed installer actively encourages "install, then delete the
download", making it worse. Fix it where it lives. **Fixed 2026-08-31; see the
next section.**

### Arguments to drop from future discussion

- *"Nexus/DeadlyStream don't host installer exes"* — **false.** DS hosts K1R's
  `K1R_1.2_Installer.exe` and HoloPatcher's `INSTALL.exe`. The case rests on
  scannability and revert, not on rules.
- *"An installer gives one-click completeness"* — it cannot install the three
  prerequisites. That failure mode is a README problem, and the README already
  handles it.
- *"Users need to swap the right files themselves"* — does not apply here. The
  mod writes nothing to `Override/` and is not per-resolution swappable; the
  patcher reads the resolution out of the exe (`RELEASE_PLAN.md` §5.1).
- **Size is a non-issue** at 12 MB zipped.

## Release shape (unchanged from what is built)

```
K1-Area-Map-Fixes-1.0.0.zip        (12 MB, single download)
└── K1-Area-Map-Fixes-1.0.0\
    ├── README.txt                 prerequisites + order, first thing you see
    ├── Install.bat                double-click; falls back to Python source
    ├── Uninstall.bat
    ├── Patcher\                   frozen, --onedir (keep it that way)
    └── More info\
        ├── TROUBLESHOOTING.txt  COMPATIBILITY.txt  TECHNICAL.txt
        ├── LICENSE (GPLv3)     SHA256SUMS.txt
        └── source\              runnable: python "More info\source\install.py"
```

DeadlyStream first (all three prerequisites live there), Nexus second. On the
page: install-order chain, Editable Executable prerequisite, Steam
"verify integrity" warning, SHA-256 of the zip, and the DS #2993 wording —
*"if you'd rather not run an executable, the Python source is in
`More info\source` and does exactly the same thing"*.

## Three proposed changes — ALL DONE 2026-08-31 (user go-ahead)

None of these altered patch bytes; `patcher/selftest.py` still reproduces md5
`435108fd…` 9/9, and `tools/verify_release.py` passes 33/33.

1. **DONE — `backup\` and `installed.json` moved to
   `%LOCALAPPDATA%\K1AreaMapFixes\`.** `manifest._home()` was split in two:
   `visible_home()` (the folder holding `Install.bat`, found by walking up, so
   it works for the frozen build one level down *and* the shipped source two)
   keeps `last-run-log.txt`; `_data_home()` places the backup and the record.
   `_data_home()` resolves in four steps — `K1AMF_HOME`; a development checkout,
   marked by `patcher/selftest.py`, which `build_release.copy_source` never
   ships, so this repo and the user's live install keep using `patcher/`; an
   `installed.json` already sitting in the release folder, so an install made by
   an older build stays revertible; otherwise `%LOCALAPPDATA%`, with a
   `~/.local/share` fallback off Windows.
2. **DONE — running from a temp/zip path is refused**, `detect.check_not_temp()`,
   called from `install.py` before anything else. **Put in the patcher, not in
   `Install.bat` as proposed**: it then also covers someone double-clicking
   `Patcher\K1AreaMapFixes.exe` directly, gets the house Refusal formatting, and
   lands in `last-run-log.txt`. `detect.temp_roots()` covers `%TEMP%`, `%TMP%`,
   `tempfile.gettempdir()`, `%LOCALAPPDATA%\Temp` and `%SystemRoot%\Temp`, which
   between them catch Explorer's `Temp1_<zip>`, 7-Zip's `7z*` and WinRAR's
   `Rar$*`. **Revert is deliberately NOT gated** — reverting from a temp copy is
   harmless now that the backup is elsewhere, and gating it would block the
   recovery route.
3. **DONE — `tools/verify_release.py` covers it**, and does not mock it:
   `%LOCALAPPDATA%` is *redirected* into `staging/`, so the code path the player
   gets is the one under test. Added checks — the record and backup land in
   `%LOCALAPPDATA%\K1AreaMapFixes` and the backup is byte-identical to the real
   pre-patch exe; the mod folder gains only `last-run-log.txt`; the game folder
   gains nothing; **the release folder is deleted and re-extracted and the mod
   uninstalls anyway** (the actual promise); running from a fake temp root is
   refused and leaves the exe alone.

---

## Open questions for next session — user-raised, NOT yet answered

### Q1. Does the mod install with no external software at all? — ANSWERED YES, 2026-08-31

**Yes. Python is not required, and the README now says so in those words.**
Two independent halves, both acceptance-tested in `tools/verify_release.py`:

- **Static.** No shipped module shells out at all — the test greps every `.py`
  under `More info\source\` for `subprocess`, `os.system`, `os.popen` and
  `shutil.which` and requires zero hits. (`_toolpath.py` only manipulates
  `sys.path`; the two `where python` calls live in `Install.bat` /
  `Uninstall.bat`, in the branch taken only when the frozen exe is absent.)
- **Runtime.** Both frozen exes run a full apply → uninstall with an
  environment built from scratch: `PATH` cut to `System32` plus `%SystemRoot%`,
  and `PYTHONHOME`/`PYTHONPATH`/`VIRTUAL_ENV` gone. The test first asserts
  `shutil.which("python")` and `("py")` both fail on that PATH, so it cannot
  pass vacuously. The apply still produces md5 `435108fd…` and the uninstall
  still returns the exe byte-exact.

**Caveat, stated plainly:** this is a stripped environment on a machine that
*does* have Python installed, not a clean VM. It proves nothing on the shipped
path reaches for a system Python or anything else outside its own folder; it
cannot prove the absence of a Windows-component dependency that happens to be
present here (PyInstaller bundles the VC runtime, so the usual suspect is
covered). A clean-VM run stays a nice-to-have, not a blocker.

### Q2. Do we link to the Editable Executable? Is that legal?

**Point 2 ANSWERED 2026-09-01, by measurement, on real hardware — GOG owners
don't need this question at all.** The user sourced a real GOG 1.03 (build
29871) install and it was diffed byte-for-byte against `downloads/swkotor.exe`:
16 differing bytes in one run at file offset `0x0AC0`, all in unmapped PE
header padding (`SizeOfHeaders`/`.text` raw start both `0x1000`) — never
mapped, never executed. **GOG's retail exe IS the Editable Executable.** Full
measurement: `docs/REVERSE_ENGINEERING.md` — "The GOG retail exe IS the
Editable Executable". Confirmed working end-to-end: full chain (UniWS → k1hrm
→ this mod) applied directly to the GOG exe with no unlocking step, run in
game at 3840x2400, Area Map and HUD minimap both PASS (Endar Spire).

So: **the prerequisite is Steam-only.** `README.txt`, `TROUBLESHOOTING.txt`,
`TECHNICAL.txt`, `COMPATIBILITY.txt` and the `detect.py:check_build` refusal
message were all rewritten 2026-09-01 to say so instead of grouping Steam and
GOG together. `RELEASE_PLAN_SIMPLE.md:30` had this right all along.

**Point 1 — the legal/naming question — ANSWERED 2026-09-01, user decision: yes,
link directly.** We will link the exe directly both in `README.txt` (already
does, see below) and in the description text on DeadlyStream and Nexus. No
further research was done to reach this decision; the earlier three-agent
web-research pass was started and aborted before any agent reported (one died
on an API error, all three were stopped to save tokens) and stays unresearched
— the user chose to proceed without it.

`README.txt:25` already links straight to the DeadlyStream file page
(`https://deadlystream.com/files/file/1320-kotor-editable-executable/`), so no
text change was needed there. **Still to do when actually uploading:** include
the same direct link in the DeadlyStream and Nexus page descriptions — no
draft of that page text exists yet.

1. **`docs/REVERSE_ENGINEERING.md` records the crack as tagged "Hellspawn
   Reborn"** (corrected 2026-08-31 — it was wrongly attributed to "FairLight"
   for months with no source; do not reintroduce that name). Whether a
   Steam-owner-only unlock tool is something to link under our own name is
   still the open legal/naming question below.

The wsgf/UniWS site declines to give a direct URL to the "cracked"/no-CD exe.
Our `README.txt` links straight to DeadlyStream #1320
(KOTOR Editable Executable, now labelled "Steam only, skip if you're on GOG").
Decide:

- is a link to a de-DRM'd `swkotor.exe` on a third-party host something we are
  willing to publish under our own name?
- DeadlyStream's own terms forbid piracy yet host this file (~399k downloads) —
  does hosting it there make linking safe for us, or just safe for them?
- alternative: **name the prerequisite and let the user search for it**, no URL.
  README already has a "if those links are dead, search DeadlyStream for the mod
  names" fallback, so the search-only route costs the user almost nothing.
- note the hard constraint already recorded in `SHIPPING.md:26`: *we* never
  redistribute a pre-patched or unpacked `swkotor.exe`. That rule is not in
  question — only whether we link to someone else's.

### Q3. The "I couldn't find your KOTOR folder" prompt — CLOSED 2026-09-01, keep as-is

User decision: leave the current wording and drag-and-drop flow unchanged, no
further polish. Current text, for the record:

```
? I couldn't find your KOTOR folder.
Easiest fix: drag your KOTOR folder onto Install.bat and let go.
(The folder with swkotor.exe in it - usually something like
 C:\Program Files (x86)\Steam\steamapps\common\swkotor)
```

To review: is drag-and-drop onto a `.bat` the right primary instruction (it works
via `%*`, but is invisible to anyone who has not done it before)? Should there be
a typed-path fallback, a Steam-library scan, or a folder-picker dialog? And does
the message survive being read by someone who has never modded anything?

---

## Provenance

Two opposing agents, read-only, 2026-08-30. Both converged on the same repo
facts; the disagreement was narrow. Key file references they surfaced:
`tools/build_release.py:10` (onedir rationale), `patcher/k1amf/manifest.py:19-50`
(backup anchoring), `patcher/k1amf/detect.py:342` (reads `Override/map.gui`,
writes nothing), `docs/SHIPPING.md:26,35-50,132-142`, `README.txt:55-77`,
`COMPATIBILITY.txt` (load order).
