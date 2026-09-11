import os
from dataclasses import dataclass


def home() -> str:
    return os.path.abspath(os.environ.get("BOOKSMITH_HOME") or os.getcwd())


def schema_dir() -> str:
    told = os.environ.get("BOOKSMITH_SCHEMA")
    if told:
        return told
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "schema"), os.path.join(here, "..", "..", "..", "schema")):
        if os.path.isdir(c):
            return os.path.abspath(c)
    raise RuntimeError("no schema directory: set BOOKSMITH_SCHEMA")


def env(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    path = os.path.join(home(), ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return default


def secrets() -> dict[str, str]:
    out = {}
    for name in ("VLM_API_KEY", "LAYOUT_API_KEY"):
        v = env(name)
        if v:
            out[name] = v
    return out


@dataclass(frozen=True)
class Settings:
    home: str
    metrics_url: str = "http://metrics:8000"
    fleet_url: str = "http://fleet:8000"
    workers: int = 2
    session_days: int = 30
    secure_cookies: bool = False

    @staticmethod
    def from_env() -> "Settings":
        h = home()
        os.makedirs(h, exist_ok=True)
        return Settings(
            home=h,
            metrics_url=(os.environ.get("BOOKSMITH_METRICS") or "http://metrics:8000").rstrip("/"),
            fleet_url=(os.environ.get("BOOKSMITH_FLEET") or "http://fleet:8000").rstrip("/"),
            workers=max(1, int(os.environ.get("BOOKSMITH_WORKERS") or 2)),
            secure_cookies=(os.environ.get("BOOKSMITH_SECURE_COOKIES") or "").lower() in ("1", "true", "yes"),
        )

    @property
    def db_path(self) -> str:
        return os.path.join(self.home, "booksmith.sqlite")

    def store_of(self, user_id: int, role: str) -> str:
        if role == "admin":
            return self.home
        store = os.path.join(self.home, "users", str(user_id))
        for sub in ("bench", "processed", "raw"):
            os.makedirs(os.path.join(store, sub), exist_ok=True)
        return store

    def relative(self, store: str) -> str:
        return os.path.relpath(store, self.home) if store != self.home else ""
