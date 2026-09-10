"""The model protocol: what a served model answers, and what a run needs of it.

A model is something that answers three routes. `describe` says what it is:
its own name, its fingerprint, the values of the knobs its own adapter read,
its vocabulary. `health` says whether it is ready and when it last worked.
`layout` takes one page and returns one `Page` in the page format. A reader
keeps the OpenAI chat route beside them. The shapes here are the contract
both sides keep: the served adapter in `processing/layout/adapters/served.py`
asks, the shim in `serving/` answers, and a stand-in in `tests/fake_layout.py`
answers to order.

Identity is what a model serves, never where it runs: `identity_of` hashes
the describe's fingerprint together with the server's knob values and the
client's, so a served run and an in-process run of one model under one
setting are one experiment, and the address the model was reached at is not
in the hash.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from collections.abc import Mapping

from booksmith.core import policy, stamp
from booksmith.core.errors import Refusal

PROTOCOL = 1
KINDS = ("layout", "reader", "hybrid")
# Whose reading order the pages carry: the model's own rank, or none.
ORDERS = ("own", "none")

# The routes, hung from the root the endpoint names. A reader's OpenAI route
# is `/v1` beside them; `root_of` takes that suffix off an endpoint.
DESCRIBE = "/booksmith/describe"
HEALTH = "/booksmith/health"
LAYOUT = "/booksmith/layout"

# What counts as a picture in a request. The `data:` type must be the right
# one: a server handed `image/png` over a JPEG answers 400.
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


def data_uri(path: str) -> tuple[str, int]:
    """A file as a data URI, and how many bytes it was."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise ValueError(
            f"{path}: I do not know this image kind. I know {sorted(MIME)}; "
            f"crops and page rasters are written by `core/raster.py`, and "
            f"those are .png")
    with open(path, "rb") as f:
        raw = f.read()
    if not raw:
        raise ValueError(
            f"{path}: the crop is empty (0 bytes). Sending it means getting "
            f"an invented answer to an empty place -- on a blank white sheet "
            f"a model produces tables, five different ones in five tries.")
    return f"data:{MIME[ext]};base64," + base64.b64encode(raw).decode(), len(raw)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: str) -> tuple[int, int] | None:
    """(width, height) out of a PNG header, or None for another kind. The
    answer to a page must be the size of the raster sent, and the header is
    the cheapest witness of what was sent."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE:
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def bearer(key: str | None) -> dict[str, str]:
    """The one header a key travels in, or none."""
    return {"Authorization": "Bearer " + key} if key else {}


def root_of(endpoint: str) -> str:
    """The root the `/booksmith` routes hang from: an OpenAI endpoint ends in
    `/v1`, and the shim serves both from one root."""
    root = endpoint.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root.rstrip("/")


def _str_map(v: object, what: str) -> dict[str, str]:
    if not isinstance(v, dict) or not all(
            isinstance(k, str) and isinstance(x, str) for k, x in v.items()):
        raise Refusal(f"describe: {what} must be a mapping of names to strings")
    return dict(v)


@dataclass
class Describe:
    """What a served model says of itself. `fingerprint` is the adapter's own,
    whole, and must carry `sha256_weights`; `knobs` are the values the server's
    adapter read under its job, name to string, as the snapshot writes them,
    and they enter the identity as read, declared here or not, since they
    decided the answer; `classes` maps every label a layout or hybrid model
    can name onto one of the tree's classes, and `vocabulary` names the
    mapping where it is one of the tree's own; `openai` says where and as
    what a reader answers the chat route, and a hybrid that carries it can
    be read through as well."""
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

    def policy(self) -> policy.Policy:
        return policy.Policy.from_classes(self.classes, self.vocabulary)

    def to_json(self) -> dict:
        return {"protocol": self.protocol, "kind": self.kind,
                "label": self.label, "fingerprint": self.fingerprint,
                "knobs": dict(self.knobs), "classes": dict(self.classes),
                "vocabulary": self.vocabulary,
                "reading_order": self.reading_order,
                "kinds": list(self.kinds), "openai": self.openai,
                "commit": self.commit, "adapter_sha256": self.adapter_sha256}

    @staticmethod
    def from_json(d: object) -> Describe:
        """The describe, or a Refusal naming the field that is wrong. Nothing
        is defaulted: a model that does not say what it is is not run."""
        if not isinstance(d, dict):
            raise Refusal("describe: the answer is not a JSON object")
        proto = d.get("protocol")
        if proto != PROTOCOL:
            raise Refusal(
                f"describe: protocol {proto!r}, and this tree speaks "
                f"{PROTOCOL}. A model of another protocol is not guessed at.")
        kind = d.get("kind")
        if kind not in KINDS:
            raise Refusal(f"describe: kind {kind!r} is not one of {KINDS}")
        label = d.get("label")
        if not isinstance(label, str) or not label.strip():
            raise Refusal("describe: no label; the model's own name is the "
                          "run directory's name, and there is no default")
        fp = d.get("fingerprint")
        if not isinstance(fp, dict) or not fp:
            raise Refusal(f"describe: {label}: the fingerprint is not a "
                          f"non-empty mapping")
        knobs = _str_map(d.get("knobs", {}), "knobs")
        classes = _str_map(d.get("classes", {}), "classes")
        foreign = sorted({c for c in classes.values() if c not in policy.CLASSES})
        if foreign:
            raise Refusal(f"describe: {label}: labels mapped onto classes "
                          f"this tree does not declare: {foreign}; the "
                          f"classes are {sorted(policy.CLASSES)}")
        order = d.get("reading_order", "none")
        if order not in ORDERS:
            raise Refusal(f"describe: {label}: reading_order {order!r} is "
                          f"not one of {ORDERS}")
        kinds = d.get("kinds", [])
        if not isinstance(kinds, list) or not all(
                isinstance(x, str) for x in kinds):
            raise Refusal(f"describe: {label}: kinds must be a list of strings")
        openai = d.get("openai")
        if kind in ("layout", "hybrid") and not classes:
            raise Refusal(f"describe: {label}: a {kind} model maps no "
                          f"labels onto classes; a label's role cannot be "
                          f"guessed")
        if kind in ("reader", "hybrid") and not kinds:
            raise Refusal(f"describe: {label}: a {kind} model says nothing "
                          f"of what kinds of content it returns")
        if kind == "reader":
            if not (isinstance(openai, dict) and isinstance(
                    openai.get("model"), str) and openai["model"]):
                raise Refusal(f"describe: {label}: a reader names no "
                              f"`openai.model`, the name the chat route "
                              f"answers to")
        commit = d.get("commit")
        sha = d.get("adapter_sha256")
        return Describe(
            kind=kind, label=label, fingerprint=fp, classes=classes,
            vocabulary=str(d.get("vocabulary") or ""), reading_order=order,
            knobs=knobs, kinds=tuple(kinds),
            openai=openai if isinstance(openai, dict) else None,
            commit=commit if isinstance(commit, str) else None,
            adapter_sha256=sha if isinstance(sha, str) else None,
            protocol=PROTOCOL)


@dataclass
class Health:
    """Ready or not, and when the model last worked: the fleet's evidence of
    use, and nothing else's."""
    ready: bool
    label: str
    last_request: float | None = None
    requests: int = 0

    def to_json(self) -> dict:
        return {"ready": self.ready, "label": self.label,
                "last_request": self.last_request, "requests": self.requests}

    @staticmethod
    def from_json(d: object) -> Health:
        if not isinstance(d, dict) or not isinstance(d.get("ready"), bool):
            raise Refusal("health: the answer carries no boolean `ready`")
        lr = d.get("last_request")
        return Health(ready=d["ready"], label=str(d.get("label") or ""),
                      last_request=float(lr) if isinstance(lr, (int, float)) else None,
                      requests=int(d.get("requests") or 0))


@dataclass
class LayoutRequest:
    """One page for a layout or hybrid model: which, at what resolution, and
    the raster as a data URI."""
    index: int
    dpi: float
    image: str

    def to_json(self) -> dict:
        return {"index": self.index, "dpi": self.dpi, "image": self.image}

    @staticmethod
    def from_json(d: object) -> LayoutRequest:
        if not isinstance(d, dict):
            raise Refusal("layout: the request is not a JSON object")
        try:
            index, dpi, image = int(d["index"]), float(d["dpi"]), d["image"]
        except (KeyError, TypeError, ValueError) as e:
            raise Refusal(f"layout: the request lacks index, dpi or image "
                          f"({type(e).__name__}: {e})") from None
        if not isinstance(image, str) or not image.startswith("data:"):
            raise Refusal("layout: `image` is not a data URI")
        return LayoutRequest(index=index, dpi=dpi, image=image)


def identity_of(describe: Describe, client_knobs: Mapping) -> str:
    """The identity of a run over a served model: the describe's fingerprint
    with the knobs the server read and the knobs the client read, together.
    A name read on both sides with two values is refused, not chosen."""
    return stamp.identity(describe.fingerprint,
                          stamp.merge_knobs(describe.knobs, client_knobs))


# --------------------------------------------------------------- delivery
class Unreachable(Exception):
    """The route did not answer with JSON: a refused connection, a timeout, a
    status other than 200, a body that does not parse. `code` is the HTTP
    status where there was one."""

    def __init__(self, url: str, why: str, code: int | None = None):
        super().__init__(f"{url}: {why}")
        self.url, self.why, self.code = url, why, code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is a refusal, not a detour: the page and any key would travel
    to an address the server named, not the operator."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect to {newurl}: not following",
            headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, body: object = None, timeout: float = 30.0,
          headers: Mapping[str, str] | None = None) -> object:
    """GET, or POST `body` as JSON, and parse the answer. Never repeats: a
    layout answer is the model's, and asking twice repairs the model."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h,
                                 method="POST" if data is not None else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")[:300]
        raise Unreachable(url, f"HTTP {e.code} {e.reason}: {text}".rstrip(": "),
                          e.code) from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Unreachable(url, f"{type(e).__name__}: {e}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Unreachable(url, f"the body did not parse as JSON "
                               f"({type(e).__name__}); first bytes {raw[:80]!r}",
                          200) from None
