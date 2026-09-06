"""Сроки аренды: два потолка, каждый из которых отбраковывал ГОДНЫЕ машины.

ПРОВЕРОК НА `remote/` НЕ БЫЛО НИ ОДНОЙ, и оба дефекта ниже нашёл не разбор
кода, а ПЛАТНЫЙ ПРОГОН 3 сентября 2026: три годные машины подряд под нож,
$0.081 и 13 минут из 60, прежде чем его остановили руками.

    зонд не поспевал        Порог отбраковки в `runner` подстраивается под наш
    за собственным порогом  канал (`min(limit, 0.5*ours)` = 0.90 Мбит/с), а
                            срок зонда был зашит: 4 МБ за 25 с. При нашем
                            канале 1.8 Мбит/с 32 мегабита идут 18 с в идеале и
                            с рукопожатием ssh в 25 не влезают. Зонд возвращал
                            0 — «тайм-аут», неотличимый от сломанной машины

    потолок внутри потолка  Подъём контейнера резался по `min(BOOT_LIMIT_S,
                            остаток)` = `min(120, 480)` = 120 с. Машина
                            49873851 успешно качала образ («Download
                            complete», «Pull complete») и была срезана на 2:12
                            при неизрасходованных 360 с бюджета попытки

Оба дефекта — один и тот же по устройству: величина, которая ДОЛЖНА выводиться
из другой, была записана числом. Проверки ниже требуют именно вывода.
"""
import inspect
import time

import support

from booksmith.remote import box as rbox
from booksmith.remote import runner


class _FakeSsh(rbox.Box):
    """Коробка, которая не ходит по ssh: считаем ТОЛЬКО срок, а не канал."""

    def __init__(self):
        self.seen = None

    _ssh = ["ssh"]
    _addr = "root@nowhere"


class _Stream:
    """Труба, отдающая байты с заданной скоростью. Заменяет ssh к машине."""

    def __init__(self, mbps, total=None):
        self.mbps, self.t0 = mbps, time.time()
        self.total, self.sent = total, 0
        self.stdout = self

    def read(self, n):
        # Сколько байт «успело прийти» к этому моменту при заданной скорости.
        must_be = int(self.mbps * 1e6 / 8 * (time.time() - self.t0))
        if self.total is not None:
            must_be = min(must_be, self.total)
        give = min(n, max(0, must_be - self.sent))
        if give == 0:
            if self.total is not None and self.sent >= self.total:
                return b""          # поток кончился
            time.sleep(0.01)
            return b"\x00"          # ещё не накопилось — но труба жива
        self.sent += give
        return b"\x00" * give

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _probe_at(mbps, seconds=0.6, total=None):
    """Прогнать настоящий `Box.probe` против трубы заданной скорости."""
    import subprocess
    was = subprocess.Popen
    subprocess.Popen = lambda *a, **k: _Stream(mbps, total)
    try:
        return _FakeSsh().probe(seconds=seconds)
    finally:
        subprocess.Popen = was


def test_a_narrow_channel_is_measured_not_called_broken():
    """Узкий канал даёт МАЛЕНЬКОЕ ЧИСЛО, а не ноль.

    Прежде зонд просил ровно 4 МБ и ждал их 25 с; не успел — возвращал 0.0, а
    ноль в `runner` значит «машина сломана». То есть «мы не успели принять»
    записывалось как «она не умеет отдавать», и отличить одно от другого было
    нельзя ПО ПОСТРОЕНИЮ. Платный прогон 3 сентября 2026 отбраковал так три
    годные машины подряд: $0.081 и 13 минут из 60.

    Умеет провалиться: верните счёт «пришло ли ровно mb мегабайт».
    """
    narrow = _probe_at(1.16)
    assert narrow > 0.5, (
        f"канал 1.16 Мбит/с измерен как {narrow:.2f} — зонд снова путает "
        f"«мы медленные» со «машина сломана»")
    assert narrow < 3.0, f"измерено {narrow:.2f} вместо ~1.16 — зонд врёт вверх"


def test_a_broken_machine_still_gives_a_number_below_any_floor():
    """Сломанная машина даёт 0.06, а не ноль — и всё равно отбраковывается.

    Зонд написан ради машины с 62 кбит/с, принявшей 3.5 МБ за семь с
    половиной минут. Сделав зонд честным, легко было сделать его слепым:
    здесь он ГОНЯЕТСЯ против такой трубы и обязан вернуть число НИЖЕ порога.
    """
    broken = _probe_at(0.062)
    assert broken < 0.3, (
        f"машина с 62 кбит/с измерена как {broken:.2f} Мбит/с — зонд "
        f"перестал отличать сломанную от медленной")
    healthy = _probe_at(50.0)
    assert healthy > 10.0, (
        f"здоровая машина измерена как {healthy:.1f} Мбит/с — зонд занижает")


def test_a_dead_channel_is_the_only_zero():
    """Ноль остаётся ровно за одним случаем: не пришло НИ БАЙТА.

    Это и есть то, о чём `runner` вправе сказать «беру другую» не сомневаясь.
    """
    assert _probe_at(0.0, total=0) == 0.0, "мёртвая труба дала не ноль"


class _FakeVast:
    """Аренда, которая ничего не арендует: ловим ТОЛЬКО переданный срок."""

    def __init__(self):
        self.boot_timeout = None

    def wait_running(self, iid, timeout):
        self.boot_timeout = timeout
        raise RuntimeError("дальше не идём: срок пойман")

    def attach_key(self, *a):
        pass


def test_connect_gives_the_boot_the_whole_attempt():
    """У попытки ОДИН срок. Второго потолка внутри него нет.

    `min(BOOT_LIMIT_S, остаток)` резал подъём по 120 с при 480 с бюджета
    попытки — и убивал машину, которая исправно качала образ («Download
    complete», «Pull complete», срезана на 2:12).

    ПОВЕДЕНИЕМ, А НЕ РАЗБОРОМ ИСХОДНИКА: первая редакция читала текст функции
    через `inspect.getsource`, и мутация, пересобирающая модуль в памяти, ей
    была не видна — батарея объявила её пойманной, ничего не проверив.
    Ловится ровно то, что уходит в `wait_running`.
    """
    v = _FakeVast()
    try:
        runner.connect(v, 1, None, None, attempt_limit=480.0)
    except RuntimeError:
        pass
    assert v.boot_timeout is not None, "wait_running не позвали вовсе"
    assert v.boot_timeout > 400.0, (
        f"подъёму отдано {v.boot_timeout:.0f} с из 480 — внутри попытки снова "
        f"стоит свой потолок, и он уже отбраковывал машины, успешно качавшие "
        f"образ")
    assert "boot_limit" not in inspect.signature(runner.connect).parameters, (
        "в connect вернулся отдельный потолок на подъём контейнера")
    assert not hasattr(runner, "BOOT_LIMIT_S"), (
        "BOOT_LIMIT_S вернулась в модуль: она не ограничивала ничего, кроме "
        "годных машин")


def _blame_with(link, best, ours, limit=None):
    """Позвать НАСТОЯЩИЙ сторож. Прямо, а не вытаскивая тело разбором.

    Первая редакция выковыривала `_blame` из `_rent` через `ast` и исполняла
    в подставном окружении — потому что сторож был заперт в замыкании. Она и
    проверяла соответственно ТЕКСТ: батарея честно сказала «НЕ ПОЙМАНА» на
    обеих мутациях, ведь те пересобирают модуль в памяти. Сторож вынесен на
    уровень модуля, и проверять стало нечего, кроме поведения.

    `limit` в подписи нет вовсе — и это тоже проверяется: решение о вечном
    списке не смеет зависеть от порога отбраковки.
    """
    recorded = []
    runner.blame_machine({"machine_id": 777}, "проба", ours=ours, link=link,
                         best_link=best,
                         mark=lambda mid, why: recorded.append((mid, why)),
                         say=lambda *a: None)
    return recorded


def test_a_machine_is_blamed_only_with_a_witness():
    """В ВЕЧНЫЙ список — только когда другая машина дала втрое больше.

    Чем оплачено (3 сентября 2026): сторож сравнивал наш HTTP-канал с
    порогом (`ours < 2*limit`), а зонд меряет ssh. Разрыв между транспортами
    у нас десятикратный — HTTP 4.6 и 2.4 против ssh 0.34 и 0.25 с ДВУХ
    РАЗНЫХ машин подряд, — и обе ушли в вечный список ни за что.
    """
    assert _blame_with(link=0.25, best=0.34, ours=4.6) == [], (
        "машина занесена НАВСЕГДА при том, что лучшая из виденных дала лишь "
        "0.34 против её 0.25 — свидетеля, что дело в машине, нет")
    assert _blame_with(link=0.25, best=7.0, ours=4.6), (
        "машина НЕ занесена, хотя другая по тому же ssh дала 7.0 против её "
        "0.25 — вот это и есть вина машины")
    assert _blame_with(link=0.25, best=7.0, ours=0.0) == [], (
        "занесли при неизмеренном своём канале")


def test_the_verdict_cannot_depend_on_the_rejection_floor():
    """Порог отбраковки в решении о вечном списке НЕ участвует.

    Прежде сторож смотрел на `limit`, и понижение порога с 2.0 до 0.4
    превращало запрет в разрешение: одна ручка на две противоположные работы.
    Теперь её нет в подписи вовсе — это и есть самая крепкая форма запрета.
    """
    import inspect
    names = set(inspect.signature(runner.blame_machine).parameters)
    assert "limit" not in names and "floor" not in names, (
        f"порог вернулся в сторож вечного списка: {sorted(names)}. Ослабляя "
        f"порог, чтобы пропустить машины, мы снова начнём легче их банить")


class _FakeVastApi:
    """Обёртка vast, которая всегда отказывает и считает обращения."""

    def __init__(self, err):
        self.err, self.calls = err, 0

    def destroy_instance(self, id):
        self.calls += 1
        raise RuntimeError(self.err)

    def show_instances(self):
        self.calls += 1
        raise RuntimeError(self.err)


def test_destroy_backs_off_instead_of_hammering():
    """Отступы между попытками РАСТУТ, и сумма меньше отсрочки дозора.

    Чем оплачено (3 сентября 2026): здесь стояла плоская пауза 4 с на пять
    попыток, а каждая делает ДВА обращения к API — уничтожение плюс проверку.
    Десять запросов за двадцать секунд. Когда vast.ai начал отвечать 403, код
    продолжил долбить с той же частотой, и ключ перестал пускать НА ВСЁ,
    включая `/users/current` (проверено `curl`-ом с тем же ключом: отказ
    пришёл от них, а не от нашей обёртки).

    Сумма отступов обязана быть МЕНЬШЕ отсрочки дозора мертвеца: если
    уничтожение не удаётся вовсе, машина гасит себя сама, и растягивать
    попытки дольше её отсрочки — значит платить за ожидание впустую.
    """
    from booksmith.remote.vast import Vast
    steps = list(Vast.RETRY_S)
    assert steps == sorted(steps) and steps[-1] > steps[0] * 4, (
        f"отступы не растут: {steps}. На отказ по частоте нельзя отвечать той "
        f"же частотой")
    assert sum(steps) < 900, (
        f"сумма отступов {sum(steps)} с не меньше отсрочки дозора мертвеца "
        f"(900 с) — ждём дольше, чем машина живёт сама")


def test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine():
    """403 и 429 зовутся ОТКАЗОМ ДОСТУПА, а не «машина не послушалась».

    Разные беды: «уничтожение не сработало» лечится повтором, «нас не
    пускают» повтором делается хуже. И проверка `alive` следом в этом случае
    отвечает «жив» просто потому, что спросить некого — это не наблюдение, а
    отсутствие наблюдения.
    """
    import time as _t

    from booksmith.remote import vast as vmod

    was_sleep, was_log = _t.sleep, vmod.log
    stated = []
    v = vmod.Vast.__new__(vmod.Vast)
    v.v = _FakeVastApi("403 Client Error: Forbidden")
    _t.sleep = lambda s: None
    vmod.log = stated.append
    try:
        assert v.destroy(1) is False
    finally:
        _t.sleep, vmod.log = was_sleep, was_log
    everything = "\n".join(stated)
    assert "ОТКАЗ ДОСТУПА" in everything, (
        f"403 назван как обычная неудача уничтожения:\n{everything[:400]}")
    assert "спросить некого" in everything, (
        "«жив» после отказа доступа выдаётся за наблюдение")


class _BoxThatFailsAfterPulse:
    """Машина, у которой пульс завёлся, а связь дальше оборвалась.

    Ровно тот случай, что оставлял брошенную машину бессмертной: пульс
    заводится ДО первой сетевой команды, а падает она штатно.
    """

    declared: list = []

    def __init__(self, *a, **kw):
        self.pulse = False
        _BoxThatFailsAfterPulse.declared.append(self)

    def wait_ready(self, **kw):
        pass

    def start_heartbeat(self):
        self.pulse = True

    def stop_heartbeat(self):
        self.pulse = False

    def check_deadman(self):
        raise OSError("ssh замолчал сразу после пульса")


def test_a_failed_connect_leaves_no_machine_with_a_live_pulse():
    """Отказ ПОСЛЕ `start_heartbeat` обязан пульс погасить.

    ЧЕМ ЭТО ОПЛАЧЕНО. `connect` заводит пульс, а следом идёт в сеть
    (`check_deadman`), и отказ там штатен. До починки `box` до вызывающего не
    доезжал — переменная в `_rent` оставалась НЕ ПРИВЯЗАНА, `stop_heartbeat`
    давал `UnboundLocalError`, и тот глушился молчащим `except Exception:
    pass`. Машина уезжала в `undead` С ЖИВЫМ ПУЛЬСОМ: наш поток стучал
    `touch /root/.alive` каждые 30 с до конца прогона и тем ВЫКЛЮЧАЛ дозор
    мертвеца — единственный из четырёх способов гашения, не зависящий ни от
    нашего ключа, ни от нашего процесса. На второй попытке хуже вдвое:
    гасился бы пульс ПРЕДЫДУЩЕЙ машины.

    Ни одной строки в журнал при этом не печаталось, то есть беда была
    невидима и по выводу.
    """
    _BoxThatFailsAfterPulse.declared = []
    was = runner.Box
    runner.Box = _BoxThatFailsAfterPulse
    try:
        for iid in (1001, 1002):
            try:
                runner.connect(_FakeVastReady(), iid, _SpecStub(), None,
                               attempt_limit=60.0)
            except OSError:
                pass
    finally:
        runner.Box = was

    declared_n = _BoxThatFailsAfterPulse.declared
    assert len(declared_n) == 2, (
        f"подставная машина заведена {len(declared_n)} раз вместо двух — "
        f"проверка не дошла до места, которое стережёт")
    live = [i for i, b in enumerate(declared_n, 1) if b.pulse]
    assert not live, (
        f"после отказа связи пульс остался жив у машин {live}. Наш поток "
        f"будет оживлять брошенную машину до конца прогона, и дозор мертвеца "
        f"на ней выключен — гасить обязан тот, кто завёл")


class _FakeVastReady:
    """Аренда, которая доводит до ssh и не мешает: беда дальше, в `Box`."""

    def wait_running(self, iid, timeout):
        pass

    def ssh_target(self, iid):
        return ("root", "10.0.0.1", 22)

    def attach_key(self, *a):
        pass


class _SpecStub:
    workdir = "/workdir"
