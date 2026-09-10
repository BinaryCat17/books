"""Books of the synthetic bench: one kind of layout and one sheet size each.

A registry and not one flat dictionary of cases; THE SHEET SIZE IS THE BOOK'S
OWN, declared here. A book declares:
    SHEET   (width, height) of the raster at 144 dpi
    ABOUT   one line: what this book is and what it is good for measuring
    CASES   {case name: function(doc, rng) -> (page, truth)}
    SPREADS the set of spread cases (a gutter shadow is drawn onto them)
    ROTATE  {case name: angle} -- what to rotate after drawing
"""
import importlib

NAMES = ("spravochnik", "slovar", "matematika", "atlas", "katalog", "zhurnal")


def load(name: str):
    """A book's module, by name."""
    if name not in NAMES:
        raise KeyError(f"no book {name!r}: there are {NAMES}")
    return importlib.import_module(f".{name}", __package__)
