"""The layer rule: which package may import which.

The table is the whole rule. `tests/contract/test_layers.py` walks every
import in the package against it; `docs/architecture.md` prints it.
"""

# package -> what it may import (itself always); a package absent is unconstrained.
MAY_IMPORT = {
    "core": (),
    "remote": ("core",),
    "processing": ("core", "remote"),
    "datasets": ("core", "processing"),
    # The model side of the protocol: a detector or a vLLM behind HTTP.
    "serving": ("core", "processing"),
    "service": ("core", "remote", "processing", "datasets"),
    # The web: users, jobs and HTTP over the service.
    "web": ("core", "remote", "processing", "datasets", "service"),
    "cli": ("core", "remote", "processing", "datasets", "service", "serving", "web"),
}

