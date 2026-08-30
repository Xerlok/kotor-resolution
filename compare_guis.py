"""Step 3: figure out what actually differs between two 'same canvas size'
resolution variants of a .gui file, by walking every control and comparing
its EXTENT (position + size) side by side.

A "control" here = any struct that has both a TAG (its name, e.g.
'LB_MODULES') and an EXTENT (its LEFT/TOP/WIDTH/HEIGHT box).
"""

import sys
from tools import keybif, gff

KEY_PATH = "source/chitin.key"
BIF_PATH = "source/data/gui.bif"


def load_gui(resref):
    key = keybif.read_key(KEY_PATH)
    entry = key.find(resref, keybif.RESTYPE_GUI)
    raw, _ = keybif.extract_resource(BIF_PATH, entry.resource_index)
    return gff.loads(raw).top


def collect_extents(struct_, path=""):
    """Walk the whole tree, return {path: (LEFT, TOP, WIDTH, HEIGHT)} for
    every struct that has a TAG + EXTENT.

    Path is built from TAG names only (never list position) — sibling
    controls get reordered between resolution variants (see mipc8x6 vs
    mipc16x12: LBL_MAP sits at a different index in each file's CONTROLS
    list), so indexing by position would wrongly treat the same control as
    two different, unmatched ones.
    """
    found = {}

    tag = struct_["TAG"] if "TAG" in struct_ else None
    if tag is not None and "EXTENT" in struct_:
        ext = struct_["EXTENT"]
        key_path = f"{path}/{tag}" if path else tag
        value = tuple(ext[f] for f in ("LEFT", "TOP", "WIDTH", "HEIGHT"))
        if key_path in found and found[key_path] != value:
            print(f"  [warn] duplicate tag path with different EXTENT: {key_path}", file=__import__("sys").stderr)
        found[key_path] = value
        path = key_path  # nest children under this control's name

    for label, f in struct_.fields.items():
        if isinstance(f.value, gff.GFFStruct):
            found.update(collect_extents(f.value, path))
        elif isinstance(f.value, list):
            for item in f.value:
                found.update(collect_extents(item, path))

    return found


if __name__ == "__main__":
    a_name, b_name = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("mainmenu8x6", "mainmenu16x12")

    a = collect_extents(load_gui(a_name))
    b = collect_extents(load_gui(b_name))

    print(f"comparing {a_name} vs {b_name}\n")
    print(f"{a_name}: {len(a)} controls found")
    print(f"{b_name}: {len(b)} controls found\n")

    all_paths = sorted(set(a) | set(b))
    diffs = 0
    for p in all_paths:
        va, vb = a.get(p), b.get(p)
        if va != vb:
            diffs += 1
            print(f"  {p}")
            print(f"    {a_name:<16} LEFT/TOP/W/H = {va}")
            print(f"    {b_name:<16} LEFT/TOP/W/H = {vb}")

    print(f"\n{diffs} of {len(all_paths)} controls differ")
