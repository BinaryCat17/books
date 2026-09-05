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
#
# ------------------------------------------------------------ дозор мертвеца
# Уничтожение инстанса до сих пор держалось на живом локальном процессе:
# блок `finally` в run_job и сторож в его же потоке.  Стоило перезапуститься
# машине оператора — и инстанс остался жить и биллиться, а задача на нём при
# этом умерла вместе с ssh.  Проверено на себе: инстанс 48131402, семь минут
# впустую.
#
# Поэтому выключатель переносится НА арендованную машину и от нас не зависит.
# vast кладёт в контейнер CONTAINER_API_KEY и CONTAINER_ID — ключ, которым
# инстанс имеет право уничтожить сам себя.  Фоновый цикл смотрит на возраст
# /root/.alive: пока оператор жив, он трогает файл каждые 30 секунд (см.
# Box.start_heartbeat).  Пропало касание дольше, чем на DEADMAN_GRACE_S, —
# машина уничтожает себя сама.
#
# Срок лежит в /root/.alive.grace отдельным файлом, а не зашит в цикл: при
# --keep инстанс нарочно остаётся без оператора, и туда пишется другое число.
DEADMAN_GRACE_S = 900

# Куда дозор докладывает, что он ВЗВЕДЁН.  Без этого файла проверить его было
# нечем: при пустом CONTAINER_API_KEY цикл жил как ни в чём не бывало и раз в
# полминуты стучал `curl -X DELETE` с пустым Bearer — то есть последний рубеж
# против утечки денег был выключен, а выглядел работающим.  Ошибки уходили в
# /root/deadman.log, которого мы не забираем.  Теперь дозор пишет о себе
# ВЕЛИЧИНАМИ (pid оболочки, в которой он крутится, id инстанса и ДЛИНУ ключа —
# длину, а не сам ключ: доклад лежит на машине и уезжает в наш лог), и
# `Box.check_deadman` читает этот файл сразу после ssh, до того как на машину
# что-то зальют.
DEADMAN_STATE = "/root/.deadman.state"

ONSTART = (
    "touch /root/.no_auto_tmux; "
    "mkdir -p {workdir}; "
    "touch /root/.alive; echo {grace} > /root/.alive.grace; "
    "(K=$CONTAINER_API_KEY; I=$CONTAINER_ID; "
    " E=/proc/1/environ; "
    " if [ -z \"$K\" ]; then "
    "   K=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_API_KEY=//p' | head -1); fi; "
    " if [ -z \"$I\" ]; then "
    "   I=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_ID=//p' | head -1); fi; "
    # Доклад пишется ИЗНУТРИ фонового цикла и прямо перед `while`: он
    # свидетельствует не о наличии переменных в onstart, а о том, что дозор
    # дожил до своего цикла с непустым ключом и непустым id.  Пустое —
    # выход с криком в файл, который мы читаем.
    # Слова доклада — ЛАТИНИЦЕЙ, и это не стиль.  Строка едет в vast через
    # API, ложится на машину файлом onstart, исполняется её оболочкой и
    # возвращается к нам через ssh; выживает ли на этом пути UTF-8, проверить
    # можно только арендой.  Ложная тревога «дозор не взведён» из-за
    # покорёженной буквы стоила бы доверия к самой тревоге.
    " if [ -z \"$K\" ] || [ -z \"$I\" ]; then "
    "   echo \"NOT-ARMED key=${{#K}} id='$I'\" > {state}; exit 1; fi; "
    " echo \"ARMED pid=$$ id=$I key=${{#K}} grace={grace}s\" > {state}; "
    " while sleep 30; do "
    # `|| echo` ловил только ОТСУТСТВИЕ файла.  Пустой файл (оборванная
    # запись) давал пустой G, `[ N -gt ]` — синтаксическую ошибку, то есть
    # ложь: машина не убивала себя никогда и молча писала ошибки в
    # /root/deadman.log, которого мы не забираем.
    "   G=$(cat /root/.alive.grace 2>/dev/null); "
    "   case \"$G\" in \'\'|0|*[!0-9]*) G={grace};; esac; "
    "   A=$(stat -c %Y /root/.alive 2>/dev/null || echo 0); "
    "   if [ $(( $(date +%s) - A )) -gt $G ]; then "
    "     curl -s -X DELETE -H \"Authorization: Bearer $K\" "
    "          https://console.vast.ai/api/v0/instances/$I/ ; "
    "   fi; "
    " done) >/root/deadman.log 2>&1 & "
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
        log(f"поиск: {q}, диск {host.disk_gb} ГБ")
        # `storage` — это диск, ПОД КОТОРЫЙ сервер считает `dph_total`
        # (`vastai/api/offers.py`: `q["allocated_storage"] = storage`), а его
        # умолчание в SDK — 5.0 ГиБ.  Мы же арендуем 60, и на этом числе
        # держатся ТРИ вещи разом: фильтр `dph_total<max_dph` (его применяет
        # сервер), наш потолок бюджета и стоимость в журнале.
        #
        # Замер на живом рынке 03.09.2026 (RTX_4090, одна и та же строка
        # запроса, отличается только `storage`; сравниваются 17 офферов,
        # попавших в ОБЕ выдачи): при 60 ГиБ цена выше на $0.013…$0.051 в
        # час — медиана $0.026, то есть 3.8% (до 8.4%).  Разброс вчетверо —
        # это цена диска у хоста, от $0.16 до $0.53 за ГБ-месяц.
        #
        # ЧЕГО ЗАМЕР НЕ ПОКАЗАЛ: порядок офферов от этого сегодня не
        # изменился — на 14 общих офферах ни один не сменил места, самый
        # дешёвый тот же.  Разная добавка у разных хостов сделать это может,
        # но утверждать, что «ранжирование выбирало не ту машину», нечем.
        # Померено другое: на те же 3.8% занижены потолок бюджета (`Budget`
        # делит деньги на `dph`), стоимость в журнале и порог
        # `dph_total<max_dph`, который применяет сервер.  Из 17 офферов
        # сегодня НИ ОДИН не перевалил через наши $0.60 от смены диска —
        # перевалил бы только тот, что стоит к потолку ближе, чем добавка.
        found = self.v.search_offers(q, order="dph_total",
                                     storage=float(host.disk_gb))
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
            # Список приоритетный, а не множество: первым идёт тот, кто у нас
            # быстрее всех считал.  Раньше здесь бралось `ranked[0]` из
            # пересечения, то есть самый дешёвый из знакомых, — а дешёвый и
            # быстрый это разные машины.
            by_machine = {}
            for o in ranked:
                by_machine.setdefault(o.get("machine_id"), o)
            for pos, mid in enumerate(prefer_machines, 1):
                if mid in by_machine:
                    log(f"машина {mid}: место {pos} в списке предпочтения "
                        f"(по журналу) — берём её")
                    return by_machine[mid]
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
            onstart_cmd=ONSTART.format(workdir=spec.workdir,
                                       grace=DEADMAN_GRACE_S,
                                       state=DEADMAN_STATE),
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
        """Описание инстанса; None — если его точно нет.

        При ошибке обращения бросаем, а не возвращаем None: вызывающий код
        отличает «ответили, что машины нет» от «не смогли спросить».  Раньше
        любая пятисотка или таймаут выглядели как «инстанса нет», и --reuse
        снимал ВТОРУЮ карту, оставив первую биллиться до своего дозора.
        Полярность здесь та же, что в alive(): неизвестность — не смерть.
        """
        rows = self.v.show_instance(id=int(iid))
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

    # Отступы РАСТУТ, а не стоят на месте. Здесь была плоская пауза в 4 с на
    # пять попыток, и каждая делает ДВА обращения к API — уничтожение плюс
    # проверку: десять запросов за двадцать секунд. Пока всё хорошо, это
    # незаметно; но стоит API начать отвечать отказом, как код продолжает
    # долбить С ТОЙ ЖЕ ЧАСТОТОЙ, то есть отвечает на ограничение частоты
    # учащением. Замер 3 сентября 2026: после такой серии ключ начал отдавать
    # 403 на ВСЁ, включая `/users/current`, и проверено `curl`-ом с тем же
    # ключом — то есть отказ пришёл от vast.ai, а не от нашей обёртки.
    #
    # Сумма отступов 2 минуты — намеренно меньше отсрочки дозора мертвеца
    # (900 с): даже если уничтожение не удастся вовсе, машина погасит себя
    # сама, и растягивать попытки дольше её отсрочки бессмысленно.
    RETRY_S = (4, 8, 16, 32, 60)

    def destroy(self, iid: int) -> bool:
        for attempt, пауза in enumerate(self.RETRY_S):
            отказ = None
            try:
                self.v.destroy_instance(id=int(iid))
            except Exception as e:
                отказ = e
                # ОТКАЗ ДОСТУПА — ЭТО ДРУГАЯ БЕДА, и звать её надо иначе.
                # «Уничтожение не сработало» значит «машина не послушалась»;
                # 403 и 429 значат «нас не пускают», и тогда бессмысленна не
                # только эта попытка, но и проверка `alive` следом — она
                # вернёт «жив» просто потому, что спросить некого.
                нас_не_пускают = any(k in str(e) for k in ("403", "429"))
                log(f"  попытка {attempt+1} уничтожить не удалась: {e}"
                    + ("  — это ОТКАЗ ДОСТУПА, а не отказ машины: дальше жду "
                       "дольше, чтобы не долбить" if нас_не_пускают else ""))
            time.sleep(пауза)
            if not self.alive(iid):
                log(f"инстанс {iid} УНИЧТОЖЕН, проверено — деньги больше не идут")
                return True
            log(f"  всё ещё жив после попытки {attempt+1}"
                + (" (или спросить некого)" if отказ else "") + ", повторяю")
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
