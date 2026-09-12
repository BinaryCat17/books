from __future__ import annotations
from dataclasses import dataclass, field
from layout import classes as policy
from layout.errors import Refusal

PROTOCOL = 1
KINDS = ("layout", "reader", "hybrid")
DESCRIBE = "/booksmith/describe"
HEALTH = "/booksmith/health"
LAYOUT = "/booksmith/layout"


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

    def policy(self) -> policy.Policy:
        return policy.Policy.from_classes(self.classes, self.vocabulary)

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
