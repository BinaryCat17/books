"""Что такое задача для арендованной машины.

Контракт намеренно узкий: раннер знает только про входные файлы, команду и
каталог с результатом.  Ничего про PDF, OCR или PaddleOCR здесь быть не должно —
иначе следующая ML-задача снова потребует переписывать аренду.
"""
from dataclasses import dataclass, field


@dataclass
class HostReq:
    """Требования к железу.  Переводится в запрос `search offers`."""

    gpu: str = "RTX_4090"
    num_gpus: int = 1
    disk_gb: int = 60
    max_dph: float = 0.60
    min_down_mbps: int = 300
    # Медленное хранилище стопорит распаковку образа: слои скачаны, а контейнер
    # всё не стартует.  Отбор по disk_bw срезал холодный старт с 14 мин до 2.5.
    min_disk_bw: int = 1500
    min_reliability: float = 0.98
    cuda_min: str = "12.9"
    machine_id: int | None = None      # прогретая машина: образ уже в её кеше
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
            f"cuda_vers>={self.cuda_min}",
        ]
        if self.machine_id:
            # Привязка к прогретой машине снимает фильтры по каналу и диску —
            # они уже не важны, образ на месте.  Но потолок цены снимать
            # нельзя: иначе прогретая машина арендуется по любой цене.
            q = [f"machine_id={self.machine_id}", f"num_gpus={self.num_gpus}",
                 "rentable=true", f"dph_total<{self.max_dph}"]
        if self.region:
            q.append(f"geolocation={self.region}")
        return " ".join(q)


@dataclass
class JobSpec:
    """Задача целиком.  Всё, что раннеру нужно знать.

    `inputs` — локальный путь -> путь относительно рабочего каталога на боксе.
    `command` выполняется в рабочем каталоге; его stdout стримится к нам.
    `outputs` — каталог на боксе, который синхронизируется обратно по ходу
    работы, а не только в конце: падение на 400-й странице из 539 должно
    оставлять 400 страниц.
    """

    name: str
    image: str
    command: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: str = "outputs"
    env: dict[str, str] = field(default_factory=dict)
    host: HostReq = field(default_factory=HostReq)

    # Оценки для ранжирования офферов и для расчёта бюджета.  Не догадки:
    # image_gb берётся из манифеста реестра, minutes — из прошлых прогонов.
    image_gb: float = 6.0
    minutes: float = 20.0

    # Жёсткие границы.  Достигнутая граница = бокс уничтожается, что бы ни шло.
    budget_usd: float = 1.00
    timeout_minutes: float = 90.0

    # Пути на боксе.  У образов PaddleOCR нет /workspace, поэтому свой каталог.
    workdir: str = "/root/ocrjob"

    def label(self) -> str:
        return f"bs-{self.name[:28]}"
