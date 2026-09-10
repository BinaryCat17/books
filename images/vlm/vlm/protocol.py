from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from collections.abc import Mapping
from vlm.errors import Refusal

PROTOCOL = 1
KINDS = ("layout", "reader", "hybrid")
ORDERS = ("own", "none")
DESCRIBE = "/booksmith/describe"
HEALTH = "/booksmith/health"


def _str_map(v: object, what: str) -> dict[str, str]:
    if not isinstance(v, dict) or not all((isinstance(k, str) and isinstance(x, str) for k, x in v.items())):
        raise Refusal(f"describe: {what} must be a mapping of names to strings")
    return dict(v)


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

    @staticmethod
    def from_json(d: object) -> Describe:
        if not isinstance(d, dict):
            raise Refusal("describe: the answer is not a JSON object")
        proto = d.get("protocol")
        if proto != PROTOCOL:
            raise Refusal(
                f"describe: protocol {proto!r}, and this tree speaks {PROTOCOL}. A model of another protocol is not guessed at."
            )
        kind = d.get("kind")
        if kind not in KINDS:
            raise Refusal(f"describe: kind {kind!r} is not one of {KINDS}")
        label = d.get("label")
        if not isinstance(label, str) or not label.strip():
            raise Refusal(
                "describe: no label; the model's own name is the run directory's name, and there is no default"
            )
        fp = d.get("fingerprint")
        if not isinstance(fp, dict) or not fp:
            raise Refusal(f"describe: {label}: the fingerprint is not a non-empty mapping")
        knobs = _str_map(d.get("knobs", {}), "knobs")
        classes = _str_map(d.get("classes", {}), "classes")
        order = d.get("reading_order", "none")
        if order not in ORDERS:
            raise Refusal(f"describe: {label}: reading_order {order!r} is not one of {ORDERS}")
        kinds = d.get("kinds", [])
        if not isinstance(kinds, list) or not all(isinstance(x, str) for x in kinds):
            raise Refusal(f"describe: {label}: kinds must be a list of strings")
        openai = d.get("openai")
        name = str(d.get("vocabulary") or "")
        if kind in ("layout", "hybrid") and (not classes):
            raise Refusal(
                f"describe: {label}: a {kind} model maps no labels onto classes; a label's role cannot be guessed"
            )
        if kind in ("reader", "hybrid") and (not kinds):
            raise Refusal(
                f"describe: {label}: a {kind} model says nothing of what kinds of content it returns"
            )
        if kind == "reader":
            if not (isinstance(openai, dict) and isinstance(openai.get("model"), str) and openai["model"]):
                raise Refusal(
                    f"describe: {label}: a reader names no `openai.model`, the name the chat route answers to"
                )
        commit = d.get("commit")
        sha = d.get("adapter_sha256")
        return Describe(
            kind=kind,
            label=label,
            fingerprint=fp,
            classes=classes,
            vocabulary=name,
            reading_order=order,
            knobs=knobs,
            kinds=tuple(kinds),
            openai=openai if isinstance(openai, dict) else None,
            commit=commit if isinstance(commit, str) else None,
            adapter_sha256=sha if isinstance(sha, str) else None,
            protocol=PROTOCOL,
        )


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

    @staticmethod
    def from_json(d: object) -> Health:
        if not isinstance(d, dict) or not isinstance(d.get("ready"), bool):
            raise Refusal("health: the answer carries no boolean `ready`")
        lr = d.get("last_request")
        return Health(
            ready=d["ready"],
            label=str(d.get("label") or ""),
            last_request=float(lr) if isinstance(lr, (int, float)) else None,
            requests=int(d.get("requests") or 0),
        )


@dataclass
class LayoutRequest:
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
            index, dpi, image = (int(d["index"]), float(d["dpi"]), d["image"])
        except (KeyError, TypeError, ValueError) as e:
            raise Refusal(
                f"layout: the request lacks index, dpi or image ({type(e).__name__}: {e})"
            ) from None
        if not isinstance(image, str) or not image.startswith("data:"):
            raise Refusal("layout: `image` is not a data URI")
        return LayoutRequest(index=index, dpi=dpi, image=image)


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
