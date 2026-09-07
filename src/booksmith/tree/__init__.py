"""Instruments over the tree itself: the Cyrillic ratchet, the prose ratio,
the import graph. Importable, so the mutation battery can break them.
"""

# Imported here so `booksmith.tree.layout` resolves as an ATTRIBUTE: the
# mutation battery swaps the module on this package, and a check that reached
# it any other way would keep the real one and certify nothing.
from booksmith.tree import layout  # noqa: E402,F401
