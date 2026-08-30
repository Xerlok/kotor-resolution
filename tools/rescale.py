"""
The actual rescaling model.

For each axis (x and y) of each control, we measure two "margins" using two
known resolutions of the same file:
  margin_start = distance from the LEFT (or TOP) edge
  margin_end   = distance from the RIGHT (or BOTTOM) edge

If margin_start stays the same at both resolutions -> anchored to that
start edge (position fixed, size fixed).
If margin_end stays the same -> anchored to the end edge (position slides
to keep that margin, size fixed).
If BOTH margins stay the same -> anchored to both edges, i.e. it STRETCHES
to keep both margins constant as the canvas grows.
Otherwise -> check if the CENTER offset stays the same -> center-anchored.

Whichever one measures closest to constant wins. We also record the exact
leftover pixel error at our reference resolution and carry it forward as a
fixed correction — this is an honest admission that a few controls were
hand-nudged by the original artist in ways our simple model can't fully
explain, but we can still reproduce them exactly at the resolution we
measured, and stay close at any other resolution.
"""

START, END, CENTER, STRETCH = "start", "end", "center", "stretch"


def _margins(pos, size, canvas_size):
    return pos, canvas_size - (pos + size)  # (margin_start, margin_end)


def classify_axis(pos_a, size_a, canvas_a, pos_b, size_b, canvas_b, tol=2):
    start_a, end_a = _margins(pos_a, size_a, canvas_a)
    start_b, end_b = _margins(pos_b, size_b, canvas_b)

    start_const = abs(start_a - start_b) <= tol
    end_const = abs(end_a - end_b) <= tol

    if start_const and end_const:
        mode, params = STRETCH, {"margin_start": start_a, "margin_end": end_a}
    elif start_const:
        mode, params = START, {"margin_start": start_a}
    elif end_const:
        mode, params = END, {"margin_end": end_a}
    else:
        center_a = (pos_a + size_a / 2) - canvas_a / 2
        center_b = (pos_b + size_b / 2) - canvas_b / 2
        mode, params = CENTER, {"center_offset": (center_a + center_b) / 2}

    predicted_b = predict_axis(mode, params, pos_a, size_a, canvas_a, canvas_b)
    correction = (pos_b - predicted_b[0], size_b - predicted_b[1])
    return {"mode": mode, "params": params, "correction": correction}


def predict_axis(mode, params, pos, size, canvas_old, canvas_new):
    if mode == START:
        return params["margin_start"], size
    if mode == END:
        new_pos = canvas_new - size - params["margin_end"]
        return new_pos, size
    if mode == STRETCH:
        new_size = canvas_new - params["margin_start"] - params["margin_end"]
        return params["margin_start"], new_size
    if mode == CENTER:
        new_pos = canvas_new / 2 + params["center_offset"] - size / 2
        return new_pos, size
    raise ValueError(mode)


def classify_control(extent_a, canvas_a, extent_b, canvas_b, tol=2):
    la, ta, wa, ha = extent_a
    lb, tb, wb, hb = extent_b
    aw, ah = canvas_a[2], canvas_a[3]
    bw, bh = canvas_b[2], canvas_b[3]
    x = classify_axis(la, wa, aw, lb, wb, bw, tol)
    y = classify_axis(ta, ha, ah, tb, hb, bh, tol)
    return {"x": x, "y": y}


def predict_control(extent, canvas_old, canvas_new, model):
    left, top, width, height = extent
    ow, oh = canvas_old[2], canvas_old[3]
    nw, nh = canvas_new[2], canvas_new[3]

    new_left, new_width = predict_axis(model["x"]["mode"], model["x"]["params"], left, width, ow, nw)
    new_top, new_height = predict_axis(model["y"]["mode"], model["y"]["params"], top, height, oh, nh)

    corr_x, corr_w = model["x"]["correction"]
    corr_y, corr_h = model["y"]["correction"]

    return (
        round(new_left + corr_x),
        round(new_top + corr_y),
        round(new_width + corr_w),
        round(new_height + corr_h),
    )
