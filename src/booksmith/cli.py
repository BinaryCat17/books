"""Единая точка входа: books <команда>.

    books offers                        посмотреть рынок, ничего не арендуя
    books ocr книга.pdf выход/          снять карту, разобрать, забрать, убить
    books ocr книга.pdf выход/ --keep   оставить машину для следующего прогона
    books ocr книга.pdf выход/ --reuse 12345
    books ls | books down 12345 | books reap
    books ledger
"""
import argparse
import os
import sys

from . import config
from .jobs import paddleocr
from .remote import ledger as ledger_mod
from .remote.runner import run_job
from .remote.spec import HostReq
from .remote.vast import Vast, log


def _host_args(ap):
    ap.add_argument("--gpu", default="RTX_4090", help="RTX_4090 / RTX_5090 / A100_PCIE ...")
    ap.add_argument("--max-dph", type=float, default=0.60, help="потолок $/час")
    ap.add_argument("--disk", type=int, default=60, help="диск инстанса, ГБ")
    ap.add_argument("--machine", type=int, help="привязаться к machine_id с прогретым кешем")
    ap.add_argument("--image", help="переопределить docker-образ")


def cmd_offers(a):
    host = HostReq(gpu=a.gpu, max_dph=a.max_dph, disk_gb=a.disk, machine_id=a.machine)
    v = Vast()
    log(f"баланс: ${v.balance():.3f}")
    warm = ledger_mod.warm_machines(a.image or paddleocr.IMAGES["mirror"])
    if warm:
        log(f"прогретые машины из журнала: {warm[:5]}")
    v.pick(host, paddleocr.IMAGE_GB, a.minutes, warm, show=8)
    return 0


def cmd_ocr(a):
    spec = paddleocr.spec(
        os.path.abspath(a.pdf), gpu=a.gpu, image=a.image, minutes=a.minutes,
        budget_usd=a.budget, disk_gb=a.disk, max_dph=a.max_dph,
        machine_id=a.machine)
    spec.timeout_minutes = a.timeout
    if not os.path.exists(a.pdf):
        raise SystemExit(f"нет файла: {a.pdf}")
    return run_job(spec, a.outdir, ssh_key=config.ssh_key(a.ssh_key),
                   keep=a.keep, reuse=a.reuse, dry_run=a.dry_run)


def cmd_local(a):
    return _run_module("booksmith.engines.pdf_layer", [a.pdf] + list(a.rest))


def cmd_mistral(a):
    return _run_module("booksmith.engines.mistral", [a.pdf, a.outdir])


def _run_module(mod: str, argv: list[str]) -> int:
    """Движки написаны как самостоятельные скрипты; зовём их как скрипты."""
    import runpy
    old = sys.argv
    sys.argv = [mod] + argv
    try:
        runpy.run_module(mod, run_name="__main__")
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        sys.argv = old


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
        log(f"  [{'ок  ' if good else 'нет '}] {name}" + ("" if good else f" — {hint}"))
        ok = ok and good

    log("проверка окружения:")
    check("rsync локально", shutil.which("rsync") is not None,
          "нужен для инкрементальной выкачки: apt install rsync")
    check("ssh локально", shutil.which("ssh") is not None, "apt install openssh-client")
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
        mb = (r.get("image_gb") or 0) * 8 * 1024 / r["setup_s"] if r.get("setup_s") else 0
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'сбой'}  "
            f"старт {r.get('setup_s',0)/60:4.1f}м ({mb:4.0f} Мбит/с)  "
            f"счёт {r.get('run_s',0)/60:5.1f}м  ${r.get('cost_usd',0):.3f}  "
            f"машина {r.get('machine_id')}")
    fit = ledger_mod.fit()
    log(f"оценка по журналу: {fit}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="books", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("offers", help="показать рынок, ничего не арендуя")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0)
    p.set_defaults(fn=cmd_offers)

    p = sub.add_parser("ocr", help="разобрать PDF на арендованной карте")
    p.add_argument("pdf")
    p.add_argument("outdir")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="ожидаемое время счёта, влияет на выбор оффера")
    p.add_argument("--budget", type=float, default=1.00,
                   help="жёсткий потолок в долларах; при достижении машина гибнет")
    p.add_argument("--timeout", type=float, default=90.0, help="потолок в минутах")
    p.add_argument("--ssh-key", default=None)
    p.add_argument("--keep", action="store_true",
                   help="оставить машину для --reuse (ДЕНЬГИ ПРОДОЛЖАЮТ ИДТИ)")
    p.add_argument("--reuse", type=int, metavar="ID",
                   help="считать на уже поднятой машине, без холодного старта")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_ocr)

    p = sub.add_parser("local", help="разобрать PDF по его же OCR-слою, без GPU")
    p.add_argument("pdf")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_local)

    p = sub.add_parser("mistral", help="разобрать PDF через Mistral OCR API")
    p.add_argument("pdf")
    p.add_argument("outdir")
    p.set_defaults(fn=cmd_mistral)

    p = sub.add_parser("ls", help="что сейчас арендовано")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="уничтожить инстанс")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="уничтожить всё, что оставили наши прогоны")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("doctor", help="проверить окружение до того, как тратить деньги")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="журнал прогонов и оценки по нему")
    p.set_defaults(fn=cmd_ledger)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
