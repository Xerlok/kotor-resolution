"""Step 4: figure out each control's "anchor" (which edge it sticks to) by
comparing the same .gui at two known resolutions, then use that to PREDICT
a third resolution's layout — and check the prediction against the real
thing, as a sanity check that our model is actually correct.

The idea, in plain terms:
  - Take a control's LEFT position at the small canvas size and the big one.
  - If LEFT didn't move at all -> it's anchored to the LEFT edge.
  - If LEFT moved by exactly the same amount the canvas got wider -> it's
    anchored to the RIGHT edge (keeping a constant distance from it).
  - If LEFT moved by exactly HALF that amount -> it's anchored to CENTER.
  - Same logic for TOP vs canvas height (top/bottom/center-vertically).
  - Width/height are assumed constant (confirmed by the earlier diff — no
    control changed size between resolutions, only position).
"""

from compare_guis import load_gui, collect_extents

LEFT, CENTER, RIGHT = "left", "center", "right"
TOP, MIDDLE, BOTTOM = "top", "middle", "bottom"

TOLERANCE = 2  # pixels of slack for hand-authored rounding


def classify(delta, canvas_delta, low_label, mid_label, high_label):
    candidates = [(0, low_label), (canvas_delta / 2, mid_label), (canvas_delta, high_label)]
    best_label, best_err = None, None
    for expected, label in candidates:
        err = abs(delta - expected)
        if best_err is None or err < best_err:
            best_err, best_label = err, label
    return best_label, best_err


def infer(a_extents, canvas_a, b_extents, canvas_b):
    """Returns {path: (anchor_x, anchor_y, width, height, err_x, err_y)}"""
    aw, ah = canvas_a[2], canvas_a[3]
    bw, bh = canvas_b[2], canvas_b[3]
    dw, dh = bw - aw, bh - ah

    result = {}
    for path in set(a_extents) & set(b_extents):
        al, at, aw_, ah_ = a_extents[path]
        bl, bt, bw_, bh_ = b_extents[path]

        ax, errx = classify(bl - al, dw, LEFT, CENTER, RIGHT)
        ay, erry = classify(bt - at, dh, TOP, MIDDLE, BOTTOM)

        result[path] = {
            "anchor_x": ax, "anchor_y": ay,
            "width": aw_, "height": ah_,
            "err_x": errx, "err_y": erry,
            "size_changed": (aw_, ah_) != (bw_, bh_),
        }
    return result


def predict(extent, anchor_x, anchor_y, canvas_old, canvas_new):
    left, top, width, height = extent
    ow, oh = canvas_old[2], canvas_old[3]
    nw, nh = canvas_new[2], canvas_new[3]
    dw, dh = nw - ow, nh - oh

    shift_x = {LEFT: 0, CENTER: dw / 2, RIGHT: dw}[anchor_x]
    shift_y = {TOP: 0, MIDDLE: dh / 2, BOTTOM: dh}[anchor_y]

    return (round(left + shift_x), round(top + shift_y), width, height)


if __name__ == "__main__":
    a = collect_extents(load_gui("mipc8x6"))
    b = collect_extents(load_gui("mipc16x12"))
    canvas_a, canvas_b = (0, 0, 800, 600), (0, 0, 1600, 1200)

    anchors = infer(a, canvas_a, b, canvas_b)

    # Summarize: how many controls fall into each anchor combo, and how many
    # didn't fit any of the 3 buckets cleanly (a bad sign for our model).
    from collections import Counter
    combo_counts = Counter((v["anchor_x"], v["anchor_y"]) for v in anchors.values())
    bad = [(p, v) for p, v in anchors.items() if v["err_x"] > TOLERANCE or v["err_y"] > TOLERANCE]
    resized = [(p, v) for p, v in anchors.items() if v["size_changed"]]

    print("Anchor combinations found:")
    for combo, count in combo_counts.most_common():
        print(f"  {combo[0]:>6} / {combo[1]:<6} : {count} controls")

    print(f"\n{len(bad)} controls didn't fit any anchor cleanly (> {TOLERANCE}px off):")
    for p, v in bad[:10]:
        print(f"  {p}: err_x={v['err_x']:.1f} err_y={v['err_y']:.1f}")

    print(f"\n{len(resized)} controls actually changed WIDTH/HEIGHT (unexpected if our model is right)")

    # --- Self-check: predict mipc16x12 FROM mipc8x6 + inferred anchors, ---
    # --- then compare against the real mipc16x12 we already have.       ---
    print("\nSelf-check: predicting mipc16x12 from mipc8x6 + inferred anchors...")
    max_err = 0
    worst = None
    for path, v in anchors.items():
        predicted = predict(a[path], v["anchor_x"], v["anchor_y"], canvas_a, canvas_b)
        actual = b[path]
        err = max(abs(p - r) for p, r in zip(predicted, actual))
        if err > max_err:
            max_err, worst = err, (path, predicted, actual)

    print(f"  worst-case pixel error across {len(anchors)} controls: {max_err}")
    print(f"  worst offender: {worst}")
