"""Secrets and paths.

Secrets live in `.env` at the project root (mode 600, not versioned). The code
only reads that file and passes the values on through stdin or the
environment, so they reach neither command arguments nor the onstart scripts
vast.ai keeps and shows in its console.
"""
import os

import booksmith

# The repository root: src/booksmith/__init__.py is three levels down.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(booksmith.__file__))))
ENV_FILE = os.path.join(ROOT, ".env")
DEFAULT_SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519_vast")


def env(name: str, default: str | None = None) -> str | None:
    """From the environment, else from .env, else the default."""
    if os.environ.get(name):
        return os.environ[name]
    # One location only, so no two places can disagree about where secrets live.
    for path in (ENV_FILE,):
        if os.path.exists(path):
            for line in open(path):
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
