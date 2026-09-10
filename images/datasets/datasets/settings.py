import os


def schema_dir() -> str:
    told = os.environ.get("BOOKSMITH_SCHEMA")
    if told:
        return told
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "schema"), os.path.join(here, "..", "..", "..", "schema")):
        if os.path.isdir(c):
            return os.path.abspath(c)
    raise RuntimeError("no schema directory: set BOOKSMITH_SCHEMA")
