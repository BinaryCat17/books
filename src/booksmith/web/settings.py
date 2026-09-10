"""What the web is configured by: the data home and a few numbers.

From the environment, never from a knob: none of this decides a run.
Sessions are random tokens kept hashed, so nothing here signs. The session
cookie is marked secure only when `BOOKSMITH_SECURE_COOKIES` says so: behind
a terminator that speaks TLS it should, and on a developer's loopback it
cannot be.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from booksmith.core import config


@dataclass(frozen=True)
class Settings:
    home: str
    workers: int = 2
    session_days: int = 30
    secure_cookies: bool = False

    @staticmethod
    def from_env() -> Settings:
        home = config.home()
        os.makedirs(home, exist_ok=True)
        workers = int(os.environ.get("BOOKSMITH_WORKERS") or 2)
        secure = (os.environ.get("BOOKSMITH_SECURE_COOKIES") or "").lower() in ("1", "true", "yes")
        return Settings(home=home, workers=max(1, workers), secure_cookies=secure)

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
