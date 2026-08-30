"""Step 1: prove the KEY/BIF reader works by listing every .gui resource
packed into gui.bif, via chitin.key."""

from tools import keybif

KEY_PATH = "source/chitin.key"

if __name__ == "__main__":
    key = keybif.read_key(KEY_PATH)

    print(f"{len(key.bif_files)} BIF files indexed, {len(key.entries)} resources total\n")

    gui_entries = key.list_by_type(keybif.RESTYPE_GUI)
    print(f"{len(gui_entries)} GUI resources found:\n")
    for e in sorted(gui_entries, key=lambda e: e.resref):
        bif_name = key.bif_files[e.bif_index].filename
        print(f"  {e.resref:<24} in {bif_name} (index {e.resource_index})")
