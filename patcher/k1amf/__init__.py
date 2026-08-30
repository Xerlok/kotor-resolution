"""K1 Area Map Fixes - the player-facing patcher.

Copyright (C) 2026 the K1 Area Map Fixes authors.
Licensed under the GNU General Public License v3 or later; see LICENSE.

This package applies THIS project's layer only. UniWS and k1hrm ("KotOR High
Resolution Menus", ndix UR) are required prerequisites: nothing of theirs is
bundled or reimplemented here, and the patcher refuses to run until it can see
that both have been applied.

Layout:
    detect.py    - find the game, read the resolution out of the exe, gate
    steps.py     - the five patch layers, applied to one in-memory image
    verify.py    - re-read from disk and prove every byte landed
    manifest.py  - what was done, so Revert can undo exactly that
"""

__version__ = "1.0.0-pre"
PRODUCT = "K1 Area Map Fixes"
