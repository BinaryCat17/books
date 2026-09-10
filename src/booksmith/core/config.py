"""Two roots, and the secrets.

`INSTALL` is where the package is: the repository on a developer's machine,
the source of the generated documents and the commit stamp, and what the
suite walks. `home()` is where the data is: the admin's store with its
`bench/`, `processed/`, `results/`, `raw/`, `models.json` and the web's
database, and the users' stores under `users/`. `BOOKSMITH_HOME` names it;
unset, the data home is the install path, and nothing changes for a
developer's tree. Not a knob: where a run is filed is not what a run does.

Secrets live in `.env` in the data home (mode 600, not versioned). The code
only reads that file and passes the values on through the job, so they
reach neither command arguments nor a snapshot.
"""
import os

import booksmith

# The repository root: src/booksmith/__init__.py is three levels down.
INSTALL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(booksmith.__file__))))
# The old name, for what means the repository: tests, documents, the commit.
ROOT = INSTALL
DEFAULT_SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519_vast")


def home() -> str:
    """The data root: `BOOKSMITH_HOME`, else the install path. Asked at each
    use, not at import, so a process that sets it before its first store
    is honoured."""
    return os.path.abspath(os.environ.get("BOOKSMITH_HOME") or INSTALL)


def env_file() -> str:
    return os.path.join(home(), ".env")


def env(name: str, default: str | None = None) -> str | None:
    """From the environment, else from `.env` in the data home, else the default."""
    if os.environ.get(name):
        return os.environ[name]
    # One location only, so no two places can disagree about where secrets live.
    path = env_file()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return default


def secrets() -> dict[str, str]:
    """What the command line hands its job: the one key `.env` may hold. The
    web builds its jobs' secrets from the model registry instead."""
    key = env("VLM_API_KEY")
    return {"VLM_API_KEY": key} if key else {}


def ssh_key(path: str | None = None) -> str | None:
    p = path or DEFAULT_SSH_KEY
    return p if os.path.exists(p) else None
