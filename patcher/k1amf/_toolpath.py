"""Make the project's `tools/` modules importable.

The patcher deliberately does NOT keep its own copy of the byte-level patch
code. Every constant it writes - cave bytes, hook sites, offsets, the match
routine - comes from the same `tools/` modules the development work and
`tools/verify_official_chain.py` use, so the shipped patcher and the binary
this project confirmed in game cannot drift apart. PyInstaller pulls those
modules into the frozen build from here.

Only stdlib-plus-capstone modules are reachable this way: `note_table_patch`
imports `map_calibration` (and therefore PyKotor) lazily, inside the one
function the patcher never calls, because the table ships frozen instead.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# repo layout: <root>/patcher/k1amf/_toolpath.py  ->  <root>/tools
# frozen layout: tools/ sits next to the bundled package
for _cand in (os.path.join(_HERE, "..", "..", "tools"),
              os.path.join(_HERE, "..", "tools"),
              os.path.join(getattr(sys, "_MEIPASS", _HERE), "tools")):
    _cand = os.path.abspath(_cand)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)
