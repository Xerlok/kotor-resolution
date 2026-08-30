"""Generate a rescaled mipc (in-game HUD) layout for an arbitrary target
resolution, built from mipc8x6 (source) using anchors learned by comparing
mipc8x6 -> mipc16x12.

This mutates a deep copy of mipc8x6's parsed structure in place (every
control's EXTENT gets recomputed) and writes it back out as valid GFF bytes.
"""

import os
import sys

from compare_guis import load_gui, collect_extents
from tools import gff, gff_writer, rescale

CANVAS_SOURCE = (0, 0, 800, 600)
CANVAS_REFERENCE = (0, 0, 1600, 1200)  # the second known point used to learn anchors


def build_models():
    a = collect_extents(load_gui("mipc8x6"))
    b = collect_extents(load_gui("mipc16x12"))
    common = set(a) & set(b)
    return {
        path: rescale.classify_control(a[path], CANVAS_SOURCE, b[path], CANVAS_REFERENCE)
        for path in common
    }, a


def apply_rescale(struct_, models, canvas_new, path=""):
    """Walk the tree, rewriting EXTENT in place wherever we have a model."""
    tag = struct_["TAG"] if "TAG" in struct_ else None
    if tag is not None and "EXTENT" in struct_:
        key_path = f"{path}/{tag}" if path else tag
        path = key_path
        if key_path in models:
            ext_struct = struct_["EXTENT"]
            old = tuple(ext_struct[f] for f in ("LEFT", "TOP", "WIDTH", "HEIGHT"))
            new = rescale.predict_control(old, CANVAS_SOURCE, canvas_new, models[key_path])
            for label, value in zip(("LEFT", "TOP", "WIDTH", "HEIGHT"), new):
                ext_struct.fields[label].value = value
        else:
            print(f"  [no model] {key_path} — leaving position unchanged", file=sys.stderr)

    for f in struct_.fields.values():
        if isinstance(f.value, gff.GFFStruct):
            apply_rescale(f.value, models, canvas_new, path)
        elif isinstance(f.value, list):
            for item in f.value:
                apply_rescale(item, models, canvas_new, path)


if __name__ == "__main__":
    target_w, target_h = (int(x) for x in sys.argv[1:3]) if len(sys.argv) > 2 else (2560, 1600)
    canvas_new = (0, 0, target_w, target_h)

    print(f"building anchor models from mipc8x6 -> mipc16x12...")
    models, source_extents = build_models()
    print(f"  {len(models)} controls modeled\n")

    print(f"generating layout for {target_w}x{target_h}...")
    from tools import keybif
    key = keybif.read_key("source/chitin.key")
    entry = key.find("mipc8x6", keybif.RESTYPE_GUI)
    raw, _ = keybif.extract_resource("source/data/gui.bif", entry.resource_index)
    parsed = gff.loads(raw)

    apply_rescale(parsed.top, models, canvas_new)

    out_bytes = gff_writer.dumps(parsed)
    os.makedirs("output", exist_ok=True)
    out_path = f"output/mipc_{target_w}x{target_h}.gui"
    with open(out_path, "wb") as f:
        f.write(out_bytes)
    print(f"wrote {out_path} ({len(out_bytes)} bytes)\n")

    # sanity check: re-read it and print a handful of key elements
    check = gff.loads(out_bytes).top
    print("sanity check (new positions):")
    for tag in ("BTN_OPT", "BTN_MINIMAP", "PB_HEALTH", "LBL_ARROW_MARGIN"):
        extents = collect_extents(check)
        matches = [v for k, v in extents.items() if k.endswith(tag)]
        if matches:
            print(f"  {tag:<18} -> {matches[0]}")
    panel = check["EXTENT"]
    print(f"  {'canvas (panel)':<18} -> {tuple(panel[f] for f in ('LEFT','TOP','WIDTH','HEIGHT'))}")
