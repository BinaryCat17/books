"""Аренда на vast.ai поверх SDK.

Раньше здесь был разбор stdout от CLI, и оттуда росла половина проблем:
`destroy instance` требовал подтверждения и **возвращал 0, даже когда
отказывался работать**, так что скрипт рапортовал об уничтожении, а деньги
продолжали идти.  В SDK этого нет — `destroy_instance(id)` ничего не
спрашивает.  Проверку повторным запросом всё равно оставляем: она стоит один
вызов, а ошибка стоит денег.
"""
import os
import re
import time

from vastai import VastAI

from . import pricing
from .spec import HostReq, JobSpec

# ssh на инстансе vast перехватывает вход и загоняет его в tmux; `ssh host 'cmd'`
# при этом печатает "no sessions" и НИЧЕГО не выполняет.  Лечится этим файлом.
# rsync ставим сразу: без него выкачивание результатов было бы неинкрементальным.
# Права на authorized_keys чинятся в фоне, а не разово: vast записывает файл
# с открытой всем маской, и момент записи не определён — он бывает и позже
# нашего onstart.  sshd читает authorized_keys на каждое подключение, так
# что достаточно починить права до первой удачной попытки.
#
# В образе то же самое снято через StrictModes no, но полагаться на это
# нельзя: vast кеширует достроенный образ по имени с тегом, и на машине
# может лежать сборка от старой версии базы.  Здесь чинится всегда.
ONSTART = (
    "touch /root/.no_auto_tmux; "
    "mkdir -p {workdir}; "
    "(for i in $(seq 1 90); do "
    "   chmod 700 /root/.ssh 2>/dev/null; "
    "   chmod 600 /root/.ssh/authorized_keys 2>/dev/null; "
    "   sleep 2; "
    " done) >/dev/null 2>&1 & "
    "(command -v rsync >/dev/null || "
    " (apt-get update -qq && apt-get install -y -qq rsync)) >/tmp/onstart.log 2>&1; "
    "sleep infinity"
)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Vast:
    def __init__(self, api_key: str | None = None):
        self.v = VastAI(api_key) if api_key else VastAI()

    # ---------------------------------------------------------------- выбор
    def offers(self, host: HostReq, image_gb: float, minutes: float,
               payload_gb: float = 0.0, warmup_s: float = 0.0) -> list[dict]:
        q = host.query()
        log(f"поиск: {q}")
        found = self.v.search_offers(q, order="dph_total")
        if not found:
            raise SystemExit(
                f"нет офферов под {host.gpu} дешевле ${host.max_dph}/час.\n"
                "Ослабь --max-dph / --min-down или возьми другую карту.")
        return pricing.rank(found, image_gb, minutes, payload_gb, warmup_s)

    def pick(self, host: HostReq, image_gb: float, minutes: float,
             prefer_machines: list[int] | None = None, show: int = 5,
             payload_gb: float = 0.0, warmup_s: float = 0.0,
             avoid: list[int] | None = None) -> dict:
        ranked = self.offers(host, image_gb, minutes, payload_gb, warmup_s)
        if avoid:
            ranked = [o for o in ranked if o.get("machine_id") not in avoid]
            if not ranked:
                raise SystemExit("годных офферов не осталось: все проверенные "
                                 "машины отсеяны по каналу")
        if prefer_machines:
            warm = [o for o in ranked if o.get("machine_id") in prefer_machines]
            if warm:
                log(f"на машине {warm[0]['machine_id']} окружение уже было — берём её")
                return warm[0]
        log("офферы по полной стоимости прогона:")
        for o in ranked[:show]:
            log("  " + pricing.describe(o))
        return ranked[0]

    # ---------------------------------------------------------------- аренда
    def create(self, offer_id: int, spec: JobSpec,
               on_created=None) -> int:
        """Создать инстанс и СРАЗУ отдать его id наружу.

        Раньше сюда же входила привязка ssh-ключа с пятью повторами по 4с.
        Всё это время инстанс уже существовал и брал деньги, а вызывающий код
        его id ещё не знал: Ctrl-C в этом окне — и уничтожать было нечего.
        """
        res = self.v.create_instance(
            id=int(offer_id),
            image=spec.image,
            disk=spec.host.disk_gb,
            label=spec.label(),
            env=spec.env or {},
            runtype="ssh_direc ssh_proxy",
            onstart_cmd=ONSTART.format(workdir=spec.workdir),
            # Без этого неудачное размещение молча создаёт ОСТАНОВЛЕННЫЙ
            # инстанс, который продолжает брать деньги за диск.
            cancel_unavail=True,
        )
        iid = res.get("new_contract")
        if not iid:
            raise SystemExit(f"создать инстанс не удалось: {res}")
        log(f"инстанс {iid} создан")
        if on_created:
            on_created(int(iid))       # до всего остального: он уже биллится
        return int(iid)

    def attach_key(self, iid: int, key_path: str) -> bool:
        """Ключ, зарегистрированный на аккаунте, в инстанс НЕ попадает.

        Его нужно привязать к конкретному инстансу, иначе получишь
        `Permission denied (publickey)` — уже после того, как выкачал образ.
        """
        pub = key_path + ".pub"
        if not os.path.exists(pub):
            log(f"  публичного ключа нет в {pub}; надеемся на ключи аккаунта")
            return False
        pubkey = open(pub).read().strip()
        for attempt in range(5):
            try:
                self.v.attach_ssh(instance_id=int(iid), ssh_key=pubkey)
                log("  ssh-ключ привязан к инстансу")
                return True
            except Exception as e:
                if attempt == 4:
                    log(f"  привязать ключ не вышло: {e}")
                time.sleep(4)
        return False

    # ---------------------------------------------------------------- статус
    def instance(self, iid: int) -> dict | None:
        try:
            rows = self.v.show_instance(id=int(iid))
        except Exception:
            return None
        return rows[0] if isinstance(rows, list) and rows else (
            rows if isinstance(rows, dict) else None)

    def wait_running(self, iid: int, timeout: float = 2100) -> dict:
        """Ждать старта контейнера.  Сюда попадает выкачивание образа.

        Ждать заодно поля `ssh_host` нельзя: часть инстансов его не публикует,
        хотя `ssh_url` при этом отвечает нормально, и цикл молча висит до
        таймаута, ничего не объясняя в логе.
        """
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            inst = self.instance(iid) or {}
            status = inst.get("actual_status")
            msg = (inst.get("status_msg") or "").strip().splitlines()
            note = msg[-1][:90] if msg else ""
            if (status, note) != last:
                log(f"  статус={status} {note}")
                last = (status, note)
            if status == "running":
                return inst
            if status in ("exited", "offline"):
                raise RuntimeError(f"инстанс {iid} умер: {inst.get('status_msg')}")
            time.sleep(10)
        raise RuntimeError(f"инстанс {iid} не поднялся за {timeout:.0f}с")

    def ssh_target(self, iid: int) -> tuple[str, str, str]:
        """Адрес машины: сначала прямой, прокси — запасной.

        `ssh_url` отдаёт прокси sshN.vast.ai, и он подводит: туннель до
        контейнера иногда не поднимается вовсе — "remote port forwarding
        failed for listen port", притом что прямой порт при этом отвечает.
        Прямой ещё и быстрее: rsync с результатом не идёт через ретранслятор.
        """
        inst = self.instance(iid) or {}
        ip = inst.get("public_ipaddr")
        mapped = (inst.get("ports") or {}).get("22/tcp") or []
        port = mapped[0].get("HostPort") if mapped else None
        if ip and port:
            return "root", str(ip).strip(), str(port)

        url = str(self.v.ssh_url(id=int(iid))).strip()
        m = re.match(r"ssh://(\w+)@([\w\.\-]+):(\d+)", url)
        if not m:
            raise RuntimeError(f"не разбирается ssh-url: {url!r}")
        log("  прямого адреса нет — иду через прокси vast")
        return m.groups()  # user, host, port

    # ------------------------------------------------------------ уничтожение
    def alive(self, iid: int) -> bool:
        """Существует ли инстанс, то есть идут ли деньги."""
        try:
            rows = self.v.show_instances()
        except Exception:
            return True          # не смогли проверить -> считаем, что жив
        return any(str(i.get("id")) == str(iid) for i in rows)

    def destroy(self, iid: int) -> bool:
        for attempt in range(5):
            try:
                self.v.destroy_instance(id=int(iid))
            except Exception as e:
                log(f"  попытка {attempt+1} уничтожить не удалась: {e}")
            time.sleep(4)
            if not self.alive(iid):
                log(f"инстанс {iid} УНИЧТОЖЕН, проверено — деньги больше не идут")
                return True
            log(f"  всё ещё жив после попытки {attempt+1}, повторяю")
        log(f"!!! НЕ СМОГ УНИЧТОЖИТЬ {iid} — С ТЕБЯ ПРОДОЛЖАЮТ БРАТЬ ДЕНЬГИ.\n"
            f"!!! Убей вручную: vastai destroy instance {iid} -y\n"
            f"!!! или https://cloud.vast.ai/instances/")
        return False

    def reap(self, prefix: str = "bs-") -> int:
        """Прибрать всё, что оставили наши прогоны."""
        rows = self.v.show_instances()
        mine = [i for i in rows if (i.get("label") or "").startswith(prefix)]
        if not mine:
            log("подбирать нечего")
            return 0
        for i in mine:
            log(f"подбираю {i['id']} ({i.get('label')})")
            self.destroy(int(i["id"]))
        return len(mine)

    def balance(self) -> float:
        return float(self.v.show_user().get("credit") or 0)
