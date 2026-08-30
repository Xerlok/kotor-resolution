"""Step 2: extract one .gui resource from gui.bif and parse it with our GFF
reader. Prints the top-level struct's fields, then drills into the first
few CONTROLS entries (if present) to see what a UI element's fields look
like — this is what we'll need to understand before we can rescale anything.
"""

import sys
from tools import keybif, gff

KEY_PATH = "source/chitin.key"
BIF_PATH = "source/data/gui.bif"


def describe(value, indent=0):
    pad = "  " * indent
    if isinstance(value, gff.GFFStruct):
        print(f"{pad}Struct(id={value.struct_id}) with {len(value.fields)} fields:")
        for label, f in value.fields.items():
            print(f"{pad}  {label:<20} type={f.type}", end="")
            if isinstance(f.value, gff.GFFStruct):
                print()
                describe(f.value, indent + 2)
            elif isinstance(f.value, list):
                print(f"  (list of {len(f.value)} structs)")
            else:
                v = f.value
                if isinstance(v, bytes):
                    v = f"<{len(v)} bytes>"
                print(f"  = {v!r}")
    else:
        print(f"{pad}{value!r}")


if __name__ == "__main__":
    resref = sys.argv[1] if len(sys.argv) > 1 else "mainmenu"

    key = keybif.read_key(KEY_PATH)
    entry = key.find(resref, keybif.RESTYPE_GUI)
    if entry is None:
        print(f"no GUI resource named {resref!r} found")
        sys.exit(1)

    raw, res_type = keybif.extract_resource(BIF_PATH, entry.resource_index)
    print(f"extracted {resref}.gui: {len(raw)} bytes, resource type {res_type}\n")

    out_path = f"output/{resref}.gui"
    import os
    os.makedirs("output", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(raw)
    print(f"saved raw bytes to {out_path}\n")

    parsed = gff.loads(raw)
    print(f"GFF FileType={parsed.file_type!r} FileVersion={parsed.file_version!r}\n")

    top = parsed.top
    print("Top-level fields:")
    for label, f in top.fields.items():
        if isinstance(f.value, list):
            print(f"  {label:<20} type={f.type}  (list of {len(f.value)} structs)")
        elif isinstance(f.value, gff.GFFStruct):
            print(f"  {label:<20} type={f.type}  (struct, {len(f.value.fields)} fields)")
        else:
            print(f"  {label:<20} type={f.type}  = {f.value!r}")

    if "CONTROLS" in top:
        controls = top["CONTROLS"]
        print(f"\nFirst control in CONTROLS ({len(controls)} total):")
        describe(controls[0], indent=1)
