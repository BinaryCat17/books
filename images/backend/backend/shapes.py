from pydantic import BaseModel


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


class RunInfo(BaseModel):
    kind: str
    label: str
    level: str
    identity: str | None
    when: str | None
    dpi: float | None
    policy: dict
    pages: list[int]
    truth: bool
    observed: bool


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
    identity: str | None
    source_sha256: str | None
    commit: str | None
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
