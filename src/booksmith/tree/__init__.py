"""Instruments over the tree itself: the import graph (`imports`) and the shape
of a book directory (`layout`). Importable, so a check can reach them as attributes.
"""

# Imported here so `booksmith.tree.layout` resolves as an ATTRIBUTE: the
# mutation battery swaps the module on this package, and a check that reached
# it any other way would keep the real one and certify nothing.
from booksmith.tree import layout  # noqa: E402,F401
