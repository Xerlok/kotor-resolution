"""Measure the Area Map's baked panel-background frame line, offline.

Confirms whether the light-blue/near-black line documented in F18
(EXPERIMENTS_AND_FAILED_APPROACHES.md) sits on the panel background art
`lbl_map` (the root TGuiPanel's BORDER.FILL, not the per-area map texture)
at the 95/640, 118/480, 535/640, 374/480 design-pixel fractions the opening
`LBL_Map` occupies, and measures its thickness in design pixels on each
side. This measurement (docs/ARCHITECTURE.md 5) decided `overscan` for the
frame-line fix (docs/FIX_IMPLEMENTATION.md Layer 6) and confirmed the line's
resolution-invariant position against the source art rather than one
screenshot.

Reads the vanilla `lbl_map` texture from the game's own
TexturePacks/swpc_tex_gui.erf, and an HD replacement .tpc/.tga if the dev
rig has one (checked in Override/, then in the vanilla-toggle stash). Both
are reported: the fix has to hold for whichever backdrop the player has.

    python tools/map_frame_art_probe.py [GAME_DIR] [OVERRIDE_LBL_MAP_PATH]
"""
import io
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pykotor.resource.formats.erf import read_erf
from pykotor.resource.formats.tpc import read_tpc, TPCTextureFormat

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
STASH_LBL_MAP = os.path.join(PROJ, "backups", "override-modded-stash", "lbl_map.tpc")

# The opening's fractions of the FULL PANEL: vanilla LBL_Map (95, 118, 440, 256)
# over a 640x480 panel (plan Sec 2 / docs/DATA_FORMATS.md "map.gui").
LEFT_FRAC = 95 / 640.0
TOP_FRAC = 118 / 480.0
RIGHT_FRAC = (95 + 440) / 640.0
BOTTOM_FRAC = (118 + 256) / 480.0

SEARCH_DESIGN_PX = 12.0  # how far either side of the expected edge to search


def _flip(img):
    # TPC (and this project's TGA convention) is stored bottom-up.
    # Getting this wrong once produced 68 phantom misplaced notes
    # (docs/ARCHITECTURE.md Sec 5) - flip before treating rows as screen Y.
    return np.asarray(img.transpose(Image.FLIP_TOP_BOTTOM), dtype=np.float64)


def _load_tpc_bytes(data):
    tpc = read_tpc(data)
    tpc.convert(TPCTextureFormat.RGBA)
    w, h = tpc.dimensions()
    img = Image.frombytes("RGBA", (w, h), bytes(tpc.get(0, 0).data)).convert("RGB")
    return _flip(img)


def _load_tga_bytes(data):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return _flip(img)


def read_vanilla_lbl_map(game_dir):
    erf_path = os.path.join(game_dir, "TexturePacks", "swpc_tex_gui.erf")
    if not os.path.exists(erf_path):
        return None, erf_path
    erf = read_erf(erf_path)
    for r in erf:
        if str(r.resref).lower() == "lbl_map":
            return _load_tpc_bytes(r.data), erf_path + " :: lbl_map"
    return None, erf_path + " (no lbl_map resref)"


def find_override_lbl_map(game_dir, explicit):
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates += [
        os.path.join(game_dir, "Override", "lbl_map.tpc"),
        os.path.join(game_dir, "Override", "lbl_map.tga"),
        STASH_LBL_MAP,
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def read_override_lbl_map(path):
    if path is None:
        return None, None
    with open(path, "rb") as fh:
        data = fh.read()
    if path.lower().endswith(".tga"):
        return _load_tga_bytes(data), path
    return _load_tpc_bytes(data), path


def measure_band(profile, expected_index, search_radius):
    """profile: (N, 3) array of RGB along a scan line, in texel order.
    Returns a dict describing the contiguous run of texels nearest
    expected_index whose colour departs from the window's own background,
    or None if nothing stands out."""
    n = len(profile)
    lo_s = max(0, int(round(expected_index - search_radius)))
    hi_s = min(n - 1, int(round(expected_index + search_radius)))
    window = profile[lo_s:hi_s + 1]
    if len(window) < 3:
        return None
    baseline = np.median(window, axis=0)
    deltas = np.linalg.norm(window - baseline, axis=1)
    # median/MAD, not mean/std: a small cluster of unrelated bright art (seen
    # on the HD override, a decorative feature ~10 design px from the true
    # line) inflates mean+std enough to mask the real, fainter line entirely.
    med = np.median(deltas)
    mad = np.median(np.abs(deltas - med))
    thresh = max(15.0, float(med + 3 * 1.4826 * mad))
    hits = np.nonzero(deltas > thresh)[0]
    if len(hits) == 0:
        return None
    centre_local = expected_index - lo_s
    runs, start, prev = [], hits[0], hits[0]
    for h in hits[1:]:
        if h != prev + 1:
            runs.append((start, prev))
            start = h
        prev = h
    runs.append((start, prev))
    lo, hi = min(runs, key=lambda r: min(abs(r[0] - centre_local), abs(r[1] - centre_local)))

    # The coarse run above tends to include a faint shoulder (a subtle shadow
    # band next to the bright highlight, seen on the HD override) that is
    # barely above background and not really "the line". Refine to
    # full-width-half-maximum around the coarse run's own peak: the standard,
    # threshold-free way to size a peak, so the reported thickness matches
    # what F18's on-screen measurement actually saw rather than every texel
    # that is merely distinguishable from background.
    peak_idx = lo + int(np.argmax(deltas[lo:hi + 1]))
    half = deltas[peak_idx] / 2.0
    lo2, hi2 = peak_idx, peak_idx
    while lo2 - 1 >= 0 and deltas[lo2 - 1] > half:
        lo2 -= 1
    while hi2 + 1 < len(deltas) and deltas[hi2 + 1] > half:
        hi2 += 1
    lo, hi = lo2, hi2

    peak = window[lo:hi + 1].mean(axis=0)
    return {
        "lo": lo + lo_s,
        "hi": hi + lo_s,
        "center": (lo + hi) / 2.0 + lo_s,
        "thickness_texels": hi - lo + 1,
        "colour": tuple(round(c) for c in peak),
        "background": tuple(round(c) for c in baseline),
    }


def measure_texture(img, label):
    h, w, _ = img.shape

    top_y, bot_y = TOP_FRAC * h, BOTTOM_FRAC * h
    mid_lo = int(top_y + (bot_y - top_y) * 0.4)
    mid_hi = int(top_y + (bot_y - top_y) * 0.6) + 1
    row_profile = img[mid_lo:mid_hi, :, :].mean(axis=0)  # (W, 3), for left/right

    left_o, right_o = LEFT_FRAC * w, RIGHT_FRAC * w
    mid_lo_x = int(left_o + (right_o - left_o) * 0.4)
    mid_hi_x = int(left_o + (right_o - left_o) * 0.6) + 1
    col_profile = img[:, mid_lo_x:mid_hi_x, :].mean(axis=1)  # (H, 3), for top/bottom

    search_x = SEARCH_DESIGN_PX / 640.0 * w
    search_y = SEARCH_DESIGN_PX / 480.0 * h

    results = {
        "left": measure_band(row_profile, left_o, search_x),
        "right": measure_band(row_profile, right_o, search_x),
        "top": measure_band(col_profile, top_y, search_y),
        "bottom": measure_band(col_profile, bot_y, search_y),
    }

    expected = {"left": LEFT_FRAC, "top": TOP_FRAC, "right": RIGHT_FRAC, "bottom": BOTTOM_FRAC}
    print("=== %s (%dx%d) ===" % (label, w, h))
    max_design_px = 0.0
    for side in ("left", "top", "right", "bottom"):
        r = results[side]
        if r is None:
            print("  %-6s NOT FOUND (no band exceeding threshold near the expected edge)" % side)
            continue
        design_span = 640.0 if side in ("left", "right") else 480.0
        frac = r["center"] / (w if side in ("left", "right") else h)
        thick_design = r["thickness_texels"] / (w if side in ("left", "right") else h) * design_span
        deviation_design_px = (frac - expected[side]) * design_span
        max_design_px = max(max_design_px, thick_design)
        print("  %-6s texel %5d..%-5d  centre frac %.5f (expected %.5f, dev %+.2f design px)  "
              "thickness %.2f design px  colour %s vs bg %s"
              % (side, r["lo"], r["hi"], frac, expected[side], deviation_design_px,
                 thick_design, r["colour"], r["background"]))
    print("  max band thickness: %.2f design px  ->  overscan = %d"
          % (max_design_px, max(1, int(np.ceil(max_design_px)))))
    return results, max_design_px


def main():
    game_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAME
    explicit_override = sys.argv[2] if len(sys.argv) > 2 else None

    vanilla, vanilla_src = read_vanilla_lbl_map(game_dir)
    overall_max = 0.0
    if vanilla is None:
        print("vanilla lbl_map NOT FOUND: %s" % vanilla_src)
    else:
        print("vanilla source: %s" % vanilla_src)
        _, max_v = measure_texture(vanilla, "vanilla")
        overall_max = max(overall_max, max_v)

    override_path = find_override_lbl_map(game_dir, explicit_override)
    override, used_path = read_override_lbl_map(override_path)
    print()
    if override is None:
        print("no Override lbl_map found (checked Override/lbl_map.tpc, "
              "Override/lbl_map.tga, and the vanilla-toggle stash) - skipped")
    else:
        stashed = os.path.normcase(used_path) == os.path.normcase(STASH_LBL_MAP)
        print("override source: %s%s" % (used_path, "  (STASHED, not currently installed)" if stashed else ""))
        _, max_o = measure_texture(override, "override")
        overall_max = max(overall_max, max_o)

    print("\noverscan (design px, both textures, minimum 1): %d"
          % max(1, int(np.ceil(overall_max))))


if __name__ == "__main__":
    main()
