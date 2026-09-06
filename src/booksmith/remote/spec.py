"""What a job for a rented machine is.

The contract is deliberately narrow: the runner knows only the input files,
the command and the directory with the result. Nothing about PDF, OCR or
PaddleOCR belongs here -- otherwise the next ML task would again demand
rewriting the rental.
"""
from dataclasses import dataclass, field


@dataclass
class HostReq:
    """Hardware requirements. Translated into a `search offers` query."""

    gpu: str = "RTX_4090"
    num_gpus: int = 1
    disk_gb: int = 60
    max_dph: float = 0.60
    # The channel became the machine's main parameter: nearly the whole
    # environment arrives over it at start, in dozens of
    # connections, pressing right against the advertised width. 639 Mbit/s
    # gave 82 seconds for 7 GB.
    min_down_mbps: int = 500
    # The disk, on the contrary, got cheap: writing 11 GB at 500 MB/s is 22 s.
    # The old threshold of 1500 cut off half the market for the sake of
    # unpacking an image we no longer unpack.
    min_disk_bw: int = 500
    min_reliability: float = 0.98
    # NO DEFAULT, and that is not an omission. The CUDA requirement is a
    # property of the TASK, not of the landlord: any number here would be
    # chosen for one model, and `remote/` must know none. It used to say
    # "12.9" -- a version for wheels long gone, overridden in exactly one
    # place (`books offers`, renting nothing), so the paying path took it.
    # Now the task says for itself.
    #
    # The price of silence: without the filter the market is wider, and an
    # unfit card is weeded out only after payment. So whoever builds the job
    # MUST set it from the model adapter -- `models/paddleocr_vl.spec()` on
    # the paying path, `cli.cmd_offers` on the one that rents nothing.
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
            # Pinning to a warmed machine drops the host QUALITY filters:
            # channel, disk bandwidth, verification, reliability. Our ledger
            # replaces them -- we have counted on this machine, and it is
            # blacklisted if it counted badly.
            #
            # Three filters must not be dropped, and used to be dropped
            # silently:
            #
            # * `cuda_vers` -- a requirement of the TASK, not of the landlord
            #   (see `cuda_min` above): a warm docker cache says nothing about
            #   the driver version;
            # * `disk_space` -- CAPACITY, not speed. An offer with less than
            #   `disk_gb` free cannot be taken, and that is learnt at creation;
            # * `gpu_name` -- a physical machine may hold several cards, and
            #   `machine_id` alone promises no particular one.
            #
            # The price ceiling stays as it was: otherwise a warmed machine is
            # rented at any price.
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

    `inputs` -- local path -> path relative to the working directory on the
    box. `command` runs in the working directory; its stdout is streamed to
    us. `outputs` -- the directory on the box synced back AS THE WORK GOES,
    not only at the end: a fall on page 400 of 539 must leave 400 pages.
    """

    name: str
    image: str
    command: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: str = "outputs"
    # What not to pull off the machine at all. Useful when the result
    # directory is mostly what we do not need: measured on an earlier run,
    # 167 MB of pictures out of a 179 MB directory. The reason is deliberately
    # without file names: the product they were made for died with the
    # markdown assembly, the field stayed general.
    #
    # The weight of every exclusion is measured dry BEFORE the pull
    # (`weigh_exclude`): a "saving" that cost four books their markup was
    # never once said out loud until it started being counted.
    pull_exclude: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    host: HostReq = field(default_factory=HostReq)

    # Estimates for ranking offers and for the budget. `minutes` comes from
    # past runs; `image_gb` is the one constant 0.06 of every ledger record,
    # which is why `ledger.link_efficiency` refuses to divide by it.
    image_gb: float = 0.06
    # Bytes the task pulls at start past docker (wheels, weights). They ride
    # a wholly different channel than the image, hence counted apart: the same
    # gigabyte takes ten times less time here.
    payload_gb: float = 0.0
    # What the task spends warming up before counting: for us, raising vLLM.
    # Normalised to 5 GHz -- it is bound by the CPU, not the
    # card, and wanders sixfold between hosts.
    warmup_s: float = 0.0
    minutes: float = 20.0

    # Hard limits: a limit reached = the box dies, whatever is running. Only
    # the term binds at these defaults, and `runner.Budget` says so aloud --
    # `max_dph` x `timeout_minutes` is $0.90 against the declared $1.00, so
    # `budget_usd` never fires.
    budget_usd: float = 1.00
    timeout_minutes: float = 90.0

    # The path on the box. Our own directory, not `/workspace`: that one is
    # not in every image, and a task counting on it falls already on the
    # rented card. The name is neutral -- it used to be `/root/ocrjob`: the
    # rental layer knew which task would ride on it.
    workdir: str = "/root/job"
    # Whether to continue the previous run's work on this machine. No by
    # default: with --reuse the same directory name otherwise passes someone
    # else's result off as ours.
    resume: bool = False

    def label(self) -> str:
        return f"bs-{self.name[:28]}"
