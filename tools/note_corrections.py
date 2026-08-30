"""Freeze the reviewed map-note corrections into the list the patch consumes.

This is the output of Phase 2b. It joins the automatic proposals from
`map_note_propose.py` with the human decisions in `output/note_decisions.csv`
and validates the result, so the exe-side table (Phase 3) is generated from
reviewed data rather than from raw proposals.

Decisions file columns: module, note_index, name, decision, target_px, decided,
reason.  decision is:
    reject    - drop the proposal, keep the vanilla position
    approve   - keep the proposal (explicit; the default for anything unlisted)
    override  - use target_px ("px,py") instead of the proposed position

A proposal the pass flagged for review (`Proposal.review`: it lands in a
different room than vanilla, moves further than REVIEW_MOVE_PX, or came from the
green-door rule) is NOT released by the default - it is reported as "awaiting
review" and stays out of the table until a row here says approve or override.

Validation performed before anything is written:
  - every correction's new world position re-projects to exactly its intended
    map pixel (the transform is not invertible by luck; this proves it)
  - every correction lands inside the engine's own draw bounds
  - the (XPosition, YPosition) key of each corrected note is unique across ALL
    340 notes in the game, so a position-keyed table cannot move the wrong note
  - the table's size against the code cave's free space

  python tools/note_corrections.py finalize [out.csv]
  python tools/note_corrections.py summary
"""

from __future__ import annotations

import os
import sys
import csv
import struct

import map_calibration as mc
import map_geometry as mg
import map_note_propose as mp

# Resolved against the project root, not the working directory: running this
# from tools/ used to silently find no decisions file and emit raw proposals.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS = os.path.join(_ROOT, "output", "note_decisions.csv")
CAVE_FREE_BYTES = 3485      # measured free space in the existing code cave
ENTRY_BYTES = 16            # oldX, oldY, newX, newY as float32


def f32(v):
    """The float32 the game actually stores - the table key must match bit for bit."""
    return struct.unpack("<f", struct.pack("<f", float(v)))[0]


def load_decisions(path=DECISIONS):
    out = {}
    if not os.path.exists(path):
        print("WARNING: no decisions file at %s - emitting RAW proposals, "
              "unreviewed" % path)
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["module"].strip(), str(row["note_index"]).strip())
            out[key] = row
    return out


def build(game=mc.DEFAULT_GAME, decisions_path=DECISIONS):
    """Returns (corrections, skipped, awaiting_review, all_note_keys, stale)."""
    decisions = load_decisions(decisions_path)
    corrections, skipped, awaiting = [], [], []
    all_keys = {}
    used_decisions = set()

    for mod, props, _geom in mp._iter_proposals(game):
        cal = mod.calibration
        for p in props:
            note = p.note
            key = (f32(note.x), f32(note.y))
            all_keys.setdefault(key, []).append((mod.name, note.index))

            dec = decisions.get((mod.name, str(note.index)))
            verdict = (dec["decision"].strip().lower() if dec else "")
            if dec:
                used_decisions.add((mod.name, str(note.index)))

            if p.rule == "none" or p.move_px < mp.MIN_MOVE_PX:
                if verdict == "override" and dec.get("target_px"):
                    pass    # a reviewer may promote a non-proposal by hand
                else:
                    continue

            if verdict == "reject":
                skipped.append((mod, p, dec["reason"]))
                continue

            # Held back by the proposal pass for a human eye (a different room
            # than vanilla, a big move, an ambiguous door - user's correction 3,
            # 2026-08-28). An explicit approve/override in the decisions file is
            # what releases it; without one it does not reach the exe table.
            if getattr(p, "review", False) and verdict not in ("approve", "override"):
                awaiting.append((mod, p))
                continue

            new_x, new_y, target = p.new_x, p.new_y, p.new_px
            source = "auto"
            if verdict == "override" and dec.get("target_px"):
                px, py = [int(v) for v in dec["target_px"].split(",")]
                new_x, new_y = cal.to_world(px, py)
                target = (px, py)
                source = "user override"
            elif verdict == "approve":
                source = "user approved"

            corrections.append({
                "module": mod.name, "area": mod.area,
                "north_axis": cal.north_axis,
                "note_index": note.index, "tag": note.tag, "strref": note.strref,
                "name": mc.strref_text(note.strref, game),
                # %.9g, not %.6f: these are float32 values and the exe table
                # keys on them BIT FOR BIT. Six decimals is too coarse for small
                # coordinates (float32 spacing near 7.0 is ~5e-7), which silently
                # shifted 17 of 172 keys by one ULP. %.9g round-trips a float32
                # exactly.
                "old_world_x": "%.9g" % f32(note.x), "old_world_y": "%.9g" % f32(note.y),
                "new_world_x": "%.9g" % new_x, "new_world_y": "%.9g" % new_y,
                "old_px": "%d,%d" % p.old_px, "new_px": "%d,%d" % target,
                "move_px": "%.1f" % p.move_px,
                "rule": p.rule, "confidence": p.confidence, "source": source,
                "reason": p.reason,
                # validation, filled below
                "roundtrip_px": "", "in_bounds": "", "key_unique": "",
                "_cal": cal, "_new": (new_x, new_y), "_target": target,
                "_key": key,
            })

    stale = set(decisions) - used_decisions
    return corrections, skipped, awaiting, all_keys, stale


def validate(corrections, all_keys):
    problems = []
    for c in corrections:
        cal = c.pop("_cal")
        new_x, new_y = c.pop("_new")
        target = c.pop("_target")
        key = c.pop("_key")

        # the game stores float32, so validate what it will actually read back
        got = cal.to_pixel(f32(new_x), f32(new_y))
        c["roundtrip_px"] = "%d,%d" % got
        ok_rt = got == tuple(target)
        ok_bounds = cal.in_bounds(*got)
        owners = all_keys.get(key, [])
        ok_key = len(owners) == 1
        c["in_bounds"] = ok_bounds
        c["key_unique"] = ok_key
        if not ok_rt:
            problems.append("%s #%d: round-trips to %s, wanted %s"
                            % (c["module"], c["note_index"], got, tuple(target)))
        if not ok_bounds:
            problems.append("%s #%d: new position is outside the draw bounds"
                            % (c["module"], c["note_index"]))
        if not ok_key:
            problems.append("%s #%d: position key shared with %s"
                            % (c["module"], c["note_index"], owners))
    return problems


def cmd_finalize(argv):
    out_csv = argv[0] if argv else os.path.join("output", "note_corrections.csv")
    corrections, skipped, awaiting, all_keys, stale = build()
    problems = validate(corrections, all_keys)

    print("reviewed corrections: %d" % len(corrections))
    print("rejected by review:   %d" % len(skipped))
    print("awaiting review:      %d (not in the table; decide them in %s)"
          % (len(awaiting), os.path.relpath(DECISIONS, _ROOT)))
    for mod, p in sorted(awaiting, key=lambda a: -a[1].move_px):
        print("   %-12s #%-3d %-24s %5.1f px  %-11s %s"
              % (mod.name, p.note.index, mc.strref_text(p.note.strref)[:24],
                 p.move_px, p.rule, p.review_reason[:70]))
    if stale:
        print("\nWARNING: %d decision row(s) match no live proposal (stale after a "
              "rule change?):" % len(stale))
        for m, i in sorted(stale):
            print("   %s #%s" % (m, i))

    print("\nvalidation:")
    print("   round-trip exact:      %d/%d"
          % (sum(1 for c in corrections if c["roundtrip_px"] == c["new_px"]), len(corrections)))
    print("   inside draw bounds:    %d/%d"
          % (sum(1 for c in corrections if c["in_bounds"] is True), len(corrections)))
    print("   position key unique:   %d/%d"
          % (sum(1 for c in corrections if c["key_unique"] is True), len(corrections)))
    if problems:
        print("\n%d PROBLEM(S):" % len(problems))
        for p in problems[:20]:
            print("   " + p)
    else:
        print("   no problems")

    size = len(corrections) * ENTRY_BYTES
    print("\nexe table: %d entries x %d B = %d B of %d B free (%d B left for code)"
          % (len(corrections), ENTRY_BYTES, size, CAVE_FREE_BYTES, CAVE_FREE_BYTES - size))

    by_rule, by_conf = {}, {}
    for c in corrections:
        by_rule[c["rule"]] = by_rule.get(c["rule"], 0) + 1
        by_conf[c["confidence"]] = by_conf.get(c["confidence"], 0) + 1
    print("\nby rule:       " + ", ".join("%s=%d" % kv for kv in sorted(by_rule.items())))
    print("by confidence: " + ", ".join("%s=%d" % kv for kv in sorted(by_conf.items())))

    if skipped:
        print("\nrejected:")
        for mod, p, reason in sorted(skipped, key=lambda s: -s[1].move_px):
            print("   %-12s #%-3d %-24s %5.1f px  %s"
                  % (mod.name, p.note.index,
                     mc.strref_text(p.note.strref)[:24], p.move_px, reason[:60]))

    fields = [k for k in corrections[0] if not k.startswith("_")]
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(corrections, key=lambda c: (c["module"], c["note_index"])))
    print("\nwrote %s (%d rows)" % (out_csv, len(corrections)))
    return 1 if problems else 0


def cmd_summary(argv):
    corrections, skipped, _awaiting, all_keys, _stale = build()
    validate(corrections, all_keys)
    print("%-12s %-4s %-26s %6s %-13s %s"
          % ("module", "#", "name", "move", "rule", "new px"))
    for c in sorted(corrections, key=lambda c: -float(c["move_px"])):
        print("%-12s %-4s %-26s %6s %-13s %s"
              % (c["module"], c["note_index"], c["name"][:26], c["move_px"],
                 c["rule"], c["new_px"]))


COMMANDS = {"finalize": cmd_finalize, "summary": cmd_summary}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
