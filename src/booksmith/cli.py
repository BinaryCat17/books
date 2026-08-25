"""Единая точка входа: books <команда>.

    books doctor                 проверить всё ДО того, как пойдут деньги
    books offers                 посмотреть рынок, ничего не арендуя
    books prepare книга.djvu     развернуть djvu в PDF, разрезав развороты
    books ls | books down 12345 | books reap
    books ledger                 журнал прогонов и оценки по нему
    books replay --check выход/  полон ли слепок входа

РАЗБОРА ЗДЕСЬ ПОКА НЕТ, и это не упущение. Прежний `books ocr` звал модель
через слой из десятка заплаток поверх чужого пайплайна и собирал книгу
эвристиками; всё это удалено вместе с замерами, которыми оправдывалось, —
они считались против вывода другой модели, а не против известного текста.
Команда вернётся, когда появится стенд, способный её судить, и метрика,
способная провалиться.
"""
import argparse
import os
import sys

from . import config
from .models import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from .remote.vast import Vast, log
from .run import replay as replay_mod


class Tee:
    """Пишет и на экран, и в файл.

    Журнал прогона нужен дважды: живым — чтобы видеть, где сейчас счёт, — и
    потом, чтобы понять, почему вышло так. До сих пор он существовал, только
    если оператор сам додумался перенаправить вывод; каталог `runs/` полон
    таких файлов с именами вроде `mv3-run.log`, то есть привычка была, а
    опоры под ней не было.
    """

    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.f = open(path, "a", encoding="utf-8", buffering=1)
        self.out = sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        return len(s)

    def flush(self):
        self.out.flush()
        self.f.flush()

    def isatty(self):
        return self.out.isatty()


def _host_args(ap):
    ap.add_argument("--gpu", default="RTX_4090",
                    help="RTX_4090 / RTX_5090 / A100_PCIE ...")
    ap.add_argument("--max-dph", type=float, default=0.60, help="потолок $/час")
    ap.add_argument("--disk", type=int, default=60, help="диск инстанса, ГБ")
    ap.add_argument("--machine", type=int,
                    help="привязаться к machine_id с прогретым кешем")
    ap.add_argument("--image", help="переопределить docker-образ")


def cmd_offers(a):
    """Показать рынок так, как его видит ранжирование. Ничего не арендует."""
    host = HostReq(gpu=a.gpu, disk_gb=a.disk, max_dph=a.max_dph,
                   machine_id=a.machine)
    host.cuda_min = paddleocr_vl.CUDA_MIN
    v = Vast()
    warm = ledger_mod.warm_machines(a.image or paddleocr_vl.BASE_IMAGE)
    v.pick(host, paddleocr_vl.IMAGE_GB, a.minutes, warm, show=8,
           payload_gb=paddleocr_vl.PAYLOAD_GB, warmup_s=paddleocr_vl.WARMUP_S)
    return 0


def cmd_prepare(a):
    """Развернуть djvu в PDF, разрезав развороты. Местно и бесплатно.

    Отдельной командой, а не только внутри разбора: развороты надо посмотреть
    глазами до того, как платить за карту. Две из трёх добавленных книг лежали
    разворотами, и распознаватель прочитал бы две страницы как одну.
    """
    from . import djvu
    print(djvu.to_pdf(a.file, dst=a.out, split=a.split))
    return 0


def cmd_ls(_a):
    v = Vast()
    rows = v.v.show_instances()
    log(f"баланс: ${v.balance():.3f}")
    if not rows:
        log("инстансов нет — денег не тратится")
        return 0
    for i in rows:
        log(f"  {i['id']}  {i.get('actual_status')}  {i.get('label')}  "
            f"${float(i.get('dph_total') or 0):.3f}/час  "
            f"машина {i.get('machine_id')}  {i.get('gpu_name')}")
    return 0


def cmd_down(a):
    return 0 if Vast().destroy(a.id) else 1


def cmd_reap(_a):
    Vast().reap()
    return 0


def cmd_doctor(_a):
    """Проверить всё, что может сорвать прогон, ДО того как деньги пойдут."""
    import shutil
    ok = True

    def check(name, good, hint=""):
        nonlocal ok
        log(f"  [{'ок  ' if good else 'нет '}] {name}"
            + ("" if good else f" — {hint}"))
        ok = ok and good

    log("проверка окружения:")
    check("rsync локально", shutil.which("rsync") is not None,
          "нужен для инкрементальной выкачки: apt install rsync")
    check("ssh локально", shutil.which("ssh") is not None,
          "apt install openssh-client")
    key = config.ssh_key()
    check(f"ssh-ключ {config.DEFAULT_SSH_KEY}", key is not None,
          "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''")
    check("публичная часть ключа", bool(key) and os.path.exists(key + ".pub"),
          "без неё ключ не привязать к инстансу")
    check(".env в корне", os.path.exists(config.ENV_FILE),
          f"скопируй .env.example в {config.ENV_FILE}")

    try:
        v = Vast()
        bal = v.balance()
        check(f"ключ vast.ai (баланс ${bal:.3f})", True)
        check("баланса хватит хотя бы на прогон", bal > 0.20,
              "пополни: console.vast.ai/billing")
        rows = v.v.show_instances()
        check(f"нет забытых инстансов (сейчас {len(rows)})", not rows,
              "books ls, затем books reap")
    except Exception as e:
        check("ключ vast.ai", False, f"vastai set api-key <КЛЮЧ> ({e})")

    log("всё в порядке" if ok else "есть проблемы — см. выше")
    return 0 if ok else 1


def cmd_ledger(_a):
    rows = ledger_mod.read()
    if not rows:
        log(f"журнал пуст ({ledger_mod.LEDGER})")
        return 0
    ok = sum(1 for r in rows if r.get("ok"))
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    log(f"{len(rows)} прогонов, успешных {ok}, потрачено ${spent:.3f}")
    for r in rows[-10:]:
        mb = ((r.get("image_gb") or 0) * 8 * 1024 / r["setup_s"]
              if r.get("setup_s") else 0)
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'сбой'}  "
            f"старт {r.get('setup_s',0)/60:4.1f}м ({mb:4.0f} Мбит/с)  "
            f"счёт {r.get('run_s',0)/60:5.1f}м  ${r.get('cost_usd',0):.3f}  "
            f"машина {r.get('machine_id')}")
    log(f"оценка по журналу: {ledger_mod.fit()}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="books", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("offers", help="показать рынок, ничего не арендуя")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="на сколько минут считать стоимость прогона")
    p.set_defaults(fn=cmd_offers)

    p = sub.add_parser("prepare", help="развернуть djvu в PDF")
    p.add_argument("file")
    p.add_argument("--out", help="куда положить PDF")
    p.add_argument("--split", default="auto", choices=("auto", "yes", "no"),
                   help="резать ли развороты")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("ls", help="что сейчас арендовано")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="уничтожить инстанс")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="уничтожить всё, что оставили наши прогоны")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("doctor",
                       help="проверить окружение до того, как тратить деньги")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="журнал прогонов и оценки по нему")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("replay", help="полон ли слепок входа для повтора")
    p.add_argument("outdir", nargs="*")
    p.add_argument("--check", action="store_true",
                   help="печатать недостающее и вернуть 1, если оно есть")
    p.set_defaults(fn=replay_mod.cmd_replay)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
