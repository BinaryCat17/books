"""The web's database: users, sessions, jobs. One sqlite file in the data
home, in write-ahead mode, one connection behind one lock.

Three tables and no more: what a book is, what a run is and what a metric
said live on disk in the shapes `core/book.py` and the metrics declare, and
the database indexes nothing of them. A job row is the record of the job;
the run directory is the record of the result.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'user')), created REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sessions(
        token_hash TEXT PRIMARY KEY, user INTEGER NOT NULL REFERENCES users(id),
        expires REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY, user INTEGER NOT NULL REFERENCES users(id),
        store TEXT NOT NULL, kind TEXT NOT NULL, book TEXT NOT NULL,
        label TEXT, model TEXT, args TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'done', 'failed', 'cancelled')),
        n INTEGER, "of" INTEGER, created REAL NOT NULL, started REAL, finished REAL,
        error TEXT, result TEXT)""",
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

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _run(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Row | None:
        row = self._run(sql, params).fetchone()
        return row

    def all(self, sql: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        return list(self._run(sql, params).fetchall())

    # ------------------------------------------------------------- users
    def add_user(self, name: str, hash_: str, role: str) -> int:
        cur = self._run("INSERT INTO users(name, hash, role, created) VALUES (?, ?, ?, ?)",
                        (name, hash_, role, time.time()))
        return int(cur.lastrowid or 0)

    def user(self, name: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM users WHERE name = ?", (name,))

    def user_by_id(self, user_id: int) -> sqlite3.Row | None:
        return self.one("SELECT * FROM users WHERE id = ?", (user_id,))

    def users(self) -> list[sqlite3.Row]:
        return self.all("SELECT id, name, role, created FROM users ORDER BY id")

    # ---------------------------------------------------------- sessions
    def open_session(self, token_hash: str, user_id: int, expires: float) -> None:
        self._run("INSERT INTO sessions(token_hash, user, expires) VALUES (?, ?, ?)",
                  (token_hash, user_id, expires))

    def session_user(self, token_hash: str) -> sqlite3.Row | None:
        """The user of a live session, or None: an expired one is closed."""
        row = self.one("SELECT s.expires, u.* FROM sessions s JOIN users u ON u.id = s.user "
                       "WHERE s.token_hash = ?", (token_hash,))
        if row is None:
            return None
        if row["expires"] < time.time():
            self.close_session(token_hash)
            return None
        return row

    def close_session(self, token_hash: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # -------------------------------------------------------------- jobs
    def add_job(self, user_id: int, store: str, kind: str, book: str,
                label: str, model: str, args: dict) -> int:
        cur = self._run(
            "INSERT INTO jobs(user, store, kind, book, label, model, args, state, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (user_id, store, kind, book, label, model, json.dumps(args), time.time()))
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

    def orphans(self) -> int:
        """Rows left running by a process that is gone: failed, and said so.
        Called once at boot, before any worker starts."""
        cur = self._run("UPDATE jobs SET state = 'failed', error = 'process died', "
                        "finished = ? WHERE state = 'running'", (time.time(),))
        return int(cur.rowcount)


def as_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = {k: row[k] for k in row.keys()}
    if "args" in d and isinstance(d["args"], str):
        d["args"] = json.loads(d["args"])
    d.pop("hash", None)
    return d
