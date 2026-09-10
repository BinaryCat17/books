import os


def home() -> str:
    return os.path.abspath(os.environ.get("BOOKSMITH_HOME") or os.getcwd())
