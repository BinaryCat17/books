import importlib

NAMES = ("spravochnik", "slovar", "matematika", "atlas", "katalog", "zhurnal")


def load(name: str):
    if name not in NAMES:
        raise KeyError(f"no book {name!r}: there are {NAMES}")
    return importlib.import_module(f".{name}", __package__)
