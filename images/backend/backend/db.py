from __future__ import annotations
import json
import sqlite3
import threading
import time
from collections.abc import Iterable

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS users(\n        id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, hash TEXT NOT NULL,\n        role TEXT NOT NULL CHECK(role IN ('admin', 'user')), created REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS sessions(\n        token_hash TEXT PRIMARY KEY, user INTEGER NOT NULL REFERENCES users(id),\n        expires REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS jobs(\n        id INTEGER PRIMARY KEY, user INTEGER NOT NULL REFERENCES users(id),\n        store TEXT NOT NULL, kind TEXT NOT NULL, book TEXT NOT NULL,\n        label TEXT, model TEXT, args TEXT NOT NULL,\n        state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'done', 'failed', 'cancelled')),\n        n INTEGER, \"of\" INTEGER, created REAL NOT NULL, started REAL, finished REAL,\n        error TEXT, result TEXT)",
    """CREATE TABLE IF NOT EXISTS measurements(
        id INTEGER PRIMARY KEY, store TEXT NOT NULL, book TEXT NOT NULL, kind TEXT NOT NULL,
        label TEXT NOT NULL, metric TEXT NOT NULL, identity TEXT, source_sha256 TEXT, truth_sha256 TEXT,
        "commit" TEXT, "when" REAL NOT NULL, pages TEXT, scalars TEXT NOT NULL, params TEXT NOT NULL)""",
)
TERMINAL = ("done", "failed", "cancelled")


class Db:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            for ddl in SCHEMA:
                self.conn.execute(ddl)
            have = {r[1] for r in self.conn.execute("PRAGMA table_info(measurements)")}
            if "truth_sha256" not in have:
                self.conn.execute("ALTER TABLE measurements ADD COLUMN truth_sha256 TEXT")

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _run(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Row | None:
        with self.lock:
            row = self.conn.execute(sql, tuple(params)).fetchone()
        return row

    def all(self, sql: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.conn.execute(sql, tuple(params)).fetchall())

    def add_user(self, name: str, hash_: str, role: str) -> int:
        cur = self._run(
            "INSERT INTO users(name, hash, role, created) VALUES (?, ?, ?, ?)",
            (name, hash_, role, time.time()),
        )
        return int(cur.lastrowid or 0)

    def user(self, name: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM users WHERE name = ?", (name,))

    def user_by_id(self, user_id: int) -> sqlite3.Row | None:
        return self.one("SELECT * FROM users WHERE id = ?", (user_id,))

    def users(self) -> list[sqlite3.Row]:
        return self.all("SELECT id, name, role, created FROM users ORDER BY id")

    def open_session(self, token_hash: str, user_id: int, expires: float) -> None:
        self._run(
            "INSERT INTO sessions(token_hash, user, expires) VALUES (?, ?, ?)",
            (token_hash, user_id, expires),
        )

    def session_user(self, token_hash: str) -> sqlite3.Row | None:
        row = self.one(
            "SELECT s.expires, u.* FROM sessions s JOIN users u ON u.id = s.user WHERE s.token_hash = ?",
            (token_hash,),
        )
        if row is None:
            return None
        if row["expires"] < time.time():
            self.close_session(token_hash)
            return None
        return row

    def close_session(self, token_hash: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def add_job(
        self, user_id: int, store: str, kind: str, book: str, label: str, model: str, args: dict
    ) -> int:
        cur = self._run(
            "INSERT INTO jobs(user, store, kind, book, label, model, args, state, created) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (user_id, store, kind, book, label, model, json.dumps(args), time.time()),
        )
        return int(cur.lastrowid or 0)

    def job(self, job_id: int) -> sqlite3.Row | None:
        return self.one("SELECT * FROM jobs WHERE id = ?", (job_id,))

    def jobs(self, user_id: int | None = None) -> list[sqlite3.Row]:
        if user_id is None:
            return self.all("SELECT * FROM jobs ORDER BY id DESC")
        return self.all("SELECT * FROM jobs WHERE user = ? ORDER BY id DESC", (user_id,))

    def set_state(self, job_id: int, state: str, **fields: object) -> None:
        cols = ["state = ?"]
        vals: list[object] = [state]
        for k, v in fields.items():
            cols.append(f'"{k}" = ?')
            vals.append(v)
        vals.append(job_id)
        self._run(f"UPDATE jobs SET {', '.join(cols)} WHERE id = ?", vals)

    def progress(self, job_id: int, n: int, of: int) -> None:
        self._run('UPDATE jobs SET n = ?, "of" = ? WHERE id = ?', (n, of, job_id))

    def claim(self, job_id: int) -> bool:
        cur = self._run(
            "UPDATE jobs SET state = 'running', started = ? WHERE id = ? AND state = 'queued'",
            (time.time(), job_id),
        )
        return cur.rowcount == 1

    def orphans(self) -> int:
        now = time.time()
        a = self._run(
            "UPDATE jobs SET state = 'failed', error = 'process died', finished = ? WHERE state = 'running'",
            (now,),
        )
        b = self._run(
            "UPDATE jobs SET state = 'failed', error = 'process died before the start', finished = ? WHERE state = 'queued'",
            (now,),
        )
        return int(a.rowcount) + int(b.rowcount)

    def add_measurements(
        self,
        store: str,
        book: str,
        kind: str,
        label: str,
        records: list[dict],
        pages: list[int] | None,
        commit: str | None,
    ) -> float:
        now = time.time()
        with self.lock:
            for r in records:
                self.conn.execute(
                    "INSERT INTO measurements(store, book, kind, label, metric, identity, source_sha256, truth_sha256, "
                    '"commit", "when", pages, scalars, params) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (
                        store,
                        book,
                        kind,
                        label,
                        r["metric"],
                        r.get("identity"),
                        r.get("source_sha256"),
                        r.get("truth_sha256"),
                        commit,
                        now,
                        json.dumps(pages) if pages is not None else None,
                        json.dumps(r["scalars"]),
                        json.dumps(r.get("params") or {}),
                    ),
                )
        return now

    def measurements(self, store: str, book: str, kind: str, label: str) -> list[sqlite3.Row]:
        return self.all(
            "SELECT * FROM measurements WHERE store = ? AND book = ? AND kind = ? AND label = ? ORDER BY id",
            (store, book, kind, label),
        )


def as_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = {k: row[k] for k in row.keys()}
    if "args" in d and isinstance(d["args"], str):
        d["args"] = json.loads(d["args"])
    for k in ("scalars", "params", "pages"):
        if k in d and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    d.pop("hash", None)
    return d
