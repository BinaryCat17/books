from dataclasses import dataclass, field


@dataclass
class HostReq:
    gpu: str = "RTX_4090"
    num_gpus: int = 1
    disk_gb: int = 60
    max_dph: float = 0.6
    min_down_mbps: int = 500
    min_disk_bw: int = 500
    min_reliability: float = 0.98
    cuda_min: str | None = None
    machine_id: int | None = None
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
            q = [
                f"machine_id={self.machine_id}",
                f"num_gpus={self.num_gpus}",
                f"gpu_name={self.gpu}",
                "rentable=true",
                f"dph_total<{self.max_dph}",
                f"disk_space>{self.disk_gb}",
            ]
            if self.cuda_min:
                q.append(f"cuda_vers>={self.cuda_min}")
        if self.region:
            q.append(f"geolocation={self.region}")
        return " ".join(q)


@dataclass
class JobSpec:
    name: str
    image: str
    command: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: str = "outputs"
    pull_exclude: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    host: HostReq = field(default_factory=HostReq)
    image_gb: float = 0.06
    payload_gb: float = 0.0
    warmup_s: float = 0.0
    minutes: float = 20.0
    budget_usd: float = 1.0
    timeout_minutes: float = 90.0
    workdir: str = "/root/job"
    resume: bool = False

    def label(self) -> str:
        return f"bs-{self.name[:28]}"
