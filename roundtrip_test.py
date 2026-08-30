"""Before trusting the writer with anything real: read a file, write it back
out, read THAT, and deep-compare against the original. If this doesn't
match, nothing built on top of the writer can be trusted."""

import sys
from tools import keybif, gff, gff_writer

KEY_PATH = "source/chitin.key"
BIF_PATH = "source/data/gui.bif"


def deep_equal(a, b, path=""):
    if isinstance(a, gff.GFFStruct):
        if not isinstance(b, gff.GFFStruct):
            return [f"{path}: expected Struct, got {type(b)}"]
        if set(a.fields) != set(b.fields):
            return [f"{path}: field sets differ: {set(a.fields) ^ set(b.fields)}"]
        errs = []
        for label in a.fields:
            errs += deep_equal(a.fields[label].value, b.fields[label].value, f"{path}/{label}")
        return errs
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: list length {len(a)} != {len(b)}"]
        errs = []
        for i, (x, y) in enumerate(zip(a, b)):
            errs += deep_equal(x, y, f"{path}[{i}]")
        return errs
    if isinstance(a, float):
        if abs(a - b) > 1e-4:
            return [f"{path}: {a!r} != {b!r}"]
        return []
    if a != b:
        return [f"{path}: {a!r} != {b!r}"]
    return []


if __name__ == "__main__":
    resref = sys.argv[1] if len(sys.argv) > 1 else "mainmenu"

    key = keybif.read_key(KEY_PATH)
    entry = key.find(resref, keybif.RESTYPE_GUI)
    original_bytes, _ = keybif.extract_resource(BIF_PATH, entry.resource_index)

    parsed_once = gff.loads(original_bytes)
    rewritten_bytes = gff_writer.dumps(parsed_once)
    parsed_twice = gff.loads(rewritten_bytes)

    errors = deep_equal(parsed_once.top, parsed_twice.top)

    print(f"{resref}.gui: original {len(original_bytes)} bytes -> rewritten {len(rewritten_bytes)} bytes")
    if errors:
        print(f"\n{len(errors)} MISMATCHES:")
        for e in errors[:20]:
            print(f"  {e}")
    else:
        print("round-trip OK: rewritten file parses back to an identical structure")
