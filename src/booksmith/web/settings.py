"""What the web is configured by: the data home, a secret, a few numbers.

From the environment, never from a knob: none of this decides a run. The
secret signs nothing yet -- sessions are random tokens stored hashed -- but
it is made once and kept in the home, so a restart keeps every session.
"""
from __future__ import annotations

import os
import secrets as _secrets
from dataclasses import dataclass

from booksmith.core import config


def _secret_file(home: str) -> str:
    path = os.path.join(home, "web.secret")
    if not os.path.isfile(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


@dataclass(frozen=True)
class Settings:
    home: str
    secret: str
    workers: int = 2
    session_days: int = 30

    @staticmethod
    def from_env() -> Settings:
        home = config.home()
        os.makedirs(home, exist_ok=True)
        secret = os.environ.get("BOOKSMITH_SECRET") or _secret_file(home)
        workers = int(os.environ.get("BOOKSMITH_WORKERS") or 2)
        return Settings(home=home, secret=secret, workers=max(1, workers))

    @property
    def db_path(self) -> str:
        return os.path.join(self.home, "booksmith.sqlite")

    def store_of(self, user_id: int, role: str) -> str:
        """A user's store: the data home for an admin, `users/<id>/` in the
        shape a store has for anyone else, made on first use."""
        if role == "admin":
            return self.home
        store = os.path.join(self.home, "users", str(user_id))
        for sub in ("bench", "processed", "results", "raw"):
            os.makedirs(os.path.join(store, sub), exist_ok=True)
        return store
