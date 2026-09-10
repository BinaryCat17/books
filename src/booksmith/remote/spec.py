"""What a job for a rented machine is.

The contract is deliberately narrow: the runner knows only the input files,
the command and the directory with the result. Nothing about PDF, OCR or
PaddleOCR belongs here, or the next ML task means rewriting the rental again.
"""
from dataclasses import dataclass, field


@dataclass
class HostReq:
    """Hardware requirements. Translated into a `search offers` query."""

    gpu: str = "RTX_4090"
    num_gpus: int = 1
    disk_gb: int = 60
    max_dph: float = 0.60
    # Nearly the whole environment arrives over the channel at start: 7 GB in
    # 82 seconds on a machine advertising 639 Mbit/s.
    min_down_mbps: int = 500
    # The disk is cheap: writing 11 GB at 500 MB/s is 22 seconds.
    min_disk_bw: int = 500
    min_reliability: float = 0.98
    # No default: the CUDA requirement is a property of the task, not of the
    # landlord, so whoever builds the job sets it from the model adapter.
    # Without the filter the market is wider and an unfit card is weeded out
    # only after payment.
    cuda_min: str | None = None
    machine_id: int | None = None      # warmed machine: image already cached
    region: str | None = None

    def query(self) -> str:
        q = [
            f"gpu_name={self.gpu}",
            f"num_gpus={self.num_gpus}",
            "rentable=true",
            "verified=true",
            f"reliability>{self.min_reliability}",
            f"dph_total<{self.max_dph}",
            f"inet_down>{self.min_down_mbps}",
            f"disk_space>{self.disk_gb}",
            f"disk_bw>{self.min_disk_bw}",
        ]
        if self.cuda_min:
            q.append(f"cuda_vers>={self.cuda_min}")
        if self.machine_id:
            # Pinning to a warmed machine drops the host quality filters --
            # channel, disk bandwidth, verification, reliability -- which the
            # ledger replaces. Three must not be dropped: `cuda_vers` belongs to
            # the task and a warm docker cache says nothing about the driver,
            # `disk_space` is capacity and not speed, `gpu_name` because a
            # machine may hold several cards. Nor may the price ceiling.
            q = [f"machine_id={self.machine_id}", f"num_gpus={self.num_gpus}",
                 f"gpu_name={self.gpu}", "rentable=true",
                 f"dph_total<{self.max_dph}",
                 f"disk_space>{self.disk_gb}"]
            if self.cuda_min:
                q.append(f"cuda_vers>={self.cuda_min}")
        if self.region:
            q.append(f"geolocation={self.region}")
        return " ".join(q)


@dataclass
class JobSpec:
    """The job whole. Everything the runner needs to know.

    `inputs` maps a local path to one relative to the working directory on the
    box, where `command` runs with its stdout streamed to us. `outputs` is the
    directory synced back as the work goes, not only at the end.
    """

    name: str
    image: str
    command: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: str = "outputs"
    # What not to pull off the machine at all, for a result directory that is
    # mostly what we do not need. Every exclusion is weighed dry before the
    # pull (`weigh_exclude`), so no saving goes unnamed.
    pull_exclude: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    host: HostReq = field(default_factory=HostReq)

    # Estimates for ranking offers and for the budget. `image_gb` is the same
    # in every record, which is why `ledger.link_efficiency` will not divide by it.
    image_gb: float = 0.06
    # Bytes pulled at start past docker (wheels, weights): a different channel
    # from the image, hence counted apart.
    payload_gb: float = 0.0
    # Warming up before the count (raising vLLM), normalised to 5 GHz: the
    # processor bounds it, not the card, and it wanders sixfold between hosts.
    warmup_s: float = 0.0
    minutes: float = 20.0

    # Hard limits: a limit reached kills the box, whatever is running. At these
    # defaults only the term binds -- $0.90 of ceiling against $1.00 of budget.
    budget_usd: float = 1.00
    timeout_minutes: float = 90.0

    # Our own directory, not `/workspace`, which is not in every image; the
    # name is neutral because the rental layer knows no task by name.
    workdir: str = "/root/job"
    # Continue the previous run's work on this machine. Off by default: with
    # --reuse the same directory name would pass someone else's result as ours.
    resume: bool = False

    def label(self) -> str:
        return f"bs-{self.name[:28]}"
