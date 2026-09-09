"""The layer rule: which package may import which.

The table is the whole rule. `tests/contract/test_layers.py` walks every
import in the package against it; `docs/architecture.md` prints it.
"""

# package -> the packages it may import (itself always). A package absent from
# the table is unconstrained.
MAY_IMPORT = {
    "core": (),
    "remote": ("core",),
    "processing": ("core", "remote"),
    "datasets": ("core", "processing"),
    "cli": ("core", "remote", "processing", "datasets"),
}

