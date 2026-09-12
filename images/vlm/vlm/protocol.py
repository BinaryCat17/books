from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from collections.abc import Mapping

PROTOCOL = 1
KINDS = ("layout", "reader", "hybrid")
DESCRIBE = "/booksmith/describe"
HEALTH = "/booksmith/health"


@dataclass
class Describe:
    kind: str
    label: str
    fingerprint: dict
    classes: dict[str, str] = field(default_factory=dict)
    vocabulary: str = ""
    reading_order: str = "none"
    knobs: dict[str, str] = field(default_factory=dict)
    kinds: tuple[str, ...] = ()
    openai: dict | None = None
    commit: str | None = None
    adapter_sha256: str | None = None
    protocol: int = PROTOCOL

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(sorted(self.classes))

    def to_json(self) -> dict:
        return {
            "protocol": self.protocol,
            "kind": self.kind,
            "label": self.label,
            "fingerprint": self.fingerprint,
            "knobs": dict(self.knobs),
            "classes": dict(self.classes),
            "vocabulary": self.vocabulary,
            "reading_order": self.reading_order,
            "kinds": list(self.kinds),
            "openai": self.openai,
            "commit": self.commit,
            "adapter_sha256": self.adapter_sha256,
        }


@dataclass
class Health:
    ready: bool
    label: str
    last_request: float | None = None
    requests: int = 0

    def to_json(self) -> dict:
        return {
            "ready": self.ready,
            "label": self.label,
            "last_request": self.last_request,
            "requests": self.requests,
        }


class Unreachable(Exception):
    def __init__(self, url: str, why: str, code: int | None = None):
        super().__init__(f"{url}: {why}")
        self.url, self.why, self.code = (url, why, code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl}: not following", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(
    url: str, body: object = None, timeout: float = 30.0, headers: Mapping[str, str] | None = None
) -> object:
    data = None if body is None else json.dumps(body).encode("utf-8")
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")[:300]
        raise Unreachable(url, f"HTTP {e.code} {e.reason}: {text}".rstrip(": "), e.code) from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Unreachable(url, f"{type(e).__name__}: {e}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Unreachable(
            url,
            f"the body did not parse as JSON ({type(e).__name__}); first bytes {raw[:80]!r}",
            200,
        ) from None
