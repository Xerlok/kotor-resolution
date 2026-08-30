"""Verify the improved (margin-based) anchor model: build it from
mipc8x6 -> mipc16x12, then check it reproduces mipc16x12 exactly (since the
correction term is measured directly from that pair, error here should be
~0 by construction — this just proves the plumbing is right end to end)."""

from compare_guis import load_gui, collect_extents
from tools import rescale

CANVAS_A = (0, 0, 800, 600)
CANVAS_B = (0, 0, 1600, 1200)

if __name__ == "__main__":
    a = collect_extents(load_gui("mipc8x6"))
    b = collect_extents(load_gui("mipc16x12"))

    common = sorted(set(a) & set(b))
    models = {
        path: rescale.classify_control(a[path], CANVAS_A, b[path], CANVAS_B)
        for path in common
    }

    max_err = 0
    for path in common:
        predicted = rescale.predict_control(a[path], CANVAS_A, CANVAS_B, models[path])
        actual = b[path]
        err = max(abs(p - r) for p, r in zip(predicted, actual))
        max_err = max(max_err, err)

    print(f"{len(common)} controls modeled")
    print(f"worst-case reconstruction error: {max_err}px (should be ~0)")

    from collections import Counter
    modes = Counter((m["x"]["mode"], m["y"]["mode"]) for m in models.values())
    print("\nanchor mode combinations:")
    for combo, count in modes.most_common():
        print(f"  x={combo[0]:<7} y={combo[1]:<7} : {count}")
