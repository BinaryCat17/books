from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    id: int
    name: str
    role: str
    created: float | None = None


class RunRow(BaseModel):
    kind: str
    label: str
    identity: str | None
    pages: int
    complete: bool
    level: str
    when: str | None


class BookRow(BaseModel):
    name: str
    runs: list[RunRow]


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor: str = Field(pattern=r"^p[0-9]{4}-b[0-9]+$")
    content: str | None = None
    label: str | None = None
    drop: Literal[True] | None = None


class CorrectionRow(Correction):
    author: str
    when: str


class Corrections(BaseModel):
    base: str
    run: str | None
    corrections: list[CorrectionRow]
    stale: bool


class RunInfo(BaseModel):
    kind: str
    label: str
    level: str
    identity: str | None
    when: str | None
    dpi: float | None
    policy: dict
    pages: list[int]
    truth: str | None
    observed: bool
    derived_from: dict | None
    corrections: list[CorrectionRow]
    stale: bool


class TruthBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: int
    box: list[float] = Field(min_length=4, max_length=4)
    label: str
    score: float | None = None
    order: int | None = None
    content: str | None = None
    kind: Literal["html", "otsl", "latex", "text", "none"] = "none"
    source_category: str | None = None


class TruthPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    width: int
    height: int
    dpi: float
    blocks: list[TruthBlock]
    raw: None = None
    meta: dict = Field(default_factory=dict)


class Layer(BaseModel):
    layer: str
    page: dict


class RunRef(BaseModel):
    kind: str
    label: str


class TruthStart(BaseModel):
    truth: str
    pages: int
    dpi: float


class Job(BaseModel):
    id: int
    user: int
    store: str
    kind: str
    book: str
    label: str | None
    model: str | None
    args: dict
    state: str
    n: int | None
    of: int | None
    created: float
    started: float | None
    finished: float | None
    error: str | None
    result: str | None


class SeriesRow(BaseModel):
    id: int
    store: str
    book: str
    kind: str
    label: str
    metric: str
    version: int
    identity: str | None
    source_sha256: str | None
    truth_sha256: str | None = None
    when: float
    pages: list[int] | None
    scalars: dict
    params: dict
    state: str


class Results(BaseModel):
    when: float
    records: list[SeriesRow]


class Preset(BaseModel):
    name: str
    kind: str
    knobs: dict[str, str]


class Placement(BaseModel):
    id: str
    model: str
    provider: str
    handle: str | None
    endpoint: str
    state: str
    started: float
    ready_at: float | None
    last_used: float
    rate_usd_h: float
    budget_usd: float
    idle_s: float
    port: int
    deadline: float | None
    why: str | None


class LedgerRow(BaseModel):
    model: str
    provider: str
    handle: str
    started: float
    stopped: float
    rate_usd_h: float
    cost_usd: float
    why: str
