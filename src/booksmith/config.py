"""Secrets and paths.

Secrets live in `.env` at the project root (mode 600, not versioned). The user
types them there in their own terminal; the code only reads the file and passes
the values on through stdin or the environment -- so they reach neither command
arguments nor the onstart scripts vast.ai keeps and shows in its console.
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_FILE = os.path.join(ROOT, ".env")
DEFAULT_SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519_vast")


def env(name: str, default: str | None = None) -> str | None:
    """From the environment, else from .env, else the default."""
    if os.environ.get(name):
        return os.environ[name]
    # ONE path, not two. The fallback `tools/.env` kept three places
    # disagreeing: the sample said put it in `tools/.env`, this file's header
    # said "at the root", a third named its own. While the fallback worked the
    # divergence hurt nobody, and so was never fixed.
    for path in (ENV_FILE,):
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return default
def ssh_key(path: str | None = None) -> str | None:
    p = path or DEFAULT_SSH_KEY
    return p if os.path.exists(p) else None
