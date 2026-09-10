"""Who is asking: a password hashed with argon2, a session as a random token
kept hashed, two roles. An anonymous request is a 401, a user on an admin's
route a 403, and neither says which of the two facts is wrong about a login.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request

from booksmith.core.errors import Refusal
from booksmith.web.db import Db

COOKIE = "booksmith_session"
ROLES = ("admin", "user")
_hasher = PasswordHasher()
# Verified against when the name is unknown, so both failures cost the same
# time and a login cannot tell a name that exists from one that does not.
_NOBODY = _hasher.hash(secrets.token_hex(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def add_user(db: Db, name: str, password: str, role: str) -> int:
    if role not in ROLES:
        raise Refusal(f"role {role!r} is not one of {ROLES}")
    if not name.strip() or not password:
        raise Refusal("a user has a name and a password")
    if db.user(name) is not None:
        raise Refusal(f"there is already a user {name!r}")
    return db.add_user(name, _hasher.hash(password), role)


def login(db: Db, name: str, password: str, days: int) -> str | None:
    """A session token, or None: the two failures answer alike."""
    row = db.user(name)
    try:
        _hasher.verify(row["hash"] if row is not None else _NOBODY, password)
    except VerifyMismatchError:
        return None
    if row is None:
        return None
    token = secrets.token_urlsafe(32)
    db.open_session(_token_hash(token), int(row["id"]), time.time() + days * 86400)
    return token


def logout(db: Db, token: str | None) -> None:
    if token:
        db.close_session(_token_hash(token))


def who(db: Db, token: str | None) -> dict | None:
    if not token:
        return None
    row = db.session_user(_token_hash(token))
    if row is None:
        return None
    return {"id": int(row["id"]), "name": row["name"], "role": row["role"]}


def require(request: Request, role: str | None = None) -> dict:
    """The user behind the request's cookie, or a status: 401 for nobody,
    403 for the wrong role."""
    user = who(request.app.state.db, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "not logged in")
    if role and user["role"] != role:
        raise HTTPException(403, f"this needs the {role} role")
    return user
