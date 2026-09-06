"""Books of the synthetic bench: one kind of layout and one sheet size each.

WHY A REGISTRY and not one flat dictionary of cases. The handbook tests one
kind of layout, and its numbers have said everything they can say
(`docs/contour-notes.md`). What is needed next are pages the handbook does not
have at all: the narrow columns of a dictionary, the matrices of a textbook,
a drawing field with its title block, a catalogue page without a line of
prose, a magazine's boxed insert.

THE SHEET SIZE IS THE BOOK'S OWN and is declared in the book's module. While
the size came from `synth`, a drawing helper called for another book would
silently draw on the handbook's format -- the same unit trap that once carried
half a spread off the edge of the sheet.

A book must declare:
    SHEET   (width, height) of the raster at 144 dpi
    ABOUT   one line: what this book is and what it is good for measuring
    CASES   {case name: function(doc, rng) -> (page, truth)}
    SPREADS the set of spread cases (a gutter shadow is drawn onto them)
    ROTATE  {case name: angle} -- what to rotate after drawing
"""
import importlib

NAMES = ("spravochnik", "slovar", "matematika", "atlas", "katalog", "zhurnal")


def load(name: str):
    """A book's module. `spravochnik` lives in `synth`, where it was born."""
    if name not in NAMES:
        raise KeyError(f"no book {name!r}: there are {NAMES}")
    if name == "spravochnik":
        from .. import synth
        return synth
    return importlib.import_module(f".{name}", __package__)
