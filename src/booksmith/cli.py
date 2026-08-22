"""Единая точка входа: books <команда>.

    books offers                        посмотреть рынок, ничего не арендуя
    books ocr книга.pdf выход/          снять карту, разобрать, забрать, убить
    books olmocr книга.pdf выход/       то же самое, но моделью olmOCR-2-7B
    books ocr книга.pdf выход/ --keep   оставить машину для следующего прогона
    books ocr книга.pdf выход/ --reuse 12345
    books ls | books down 12345 | books reap
    books ledger
"""
import argparse
import glob
import os
import re
import shutil
import sys
import time

from . import config, layout
from .jobs import olmocr, paddleocr
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
    host.cuda_min = "13.0"          # колёса torch — под CUDA 13, как и в задаче
    v = Vast()
    log(f"баланс: ${v.balance():.3f}")
    warm = ledger_mod.warm_machines(a.image or paddleocr.BASE_IMAGE)
    if warm:
        log(f"прогретые машины из журнала: {warm[:5]}")
    v.pick(host, paddleocr.IMAGE_GB, a.minutes, warm, show=8,
           payload_gb=paddleocr.PAYLOAD_GB, warmup_s=paddleocr.WARMUP_S)
    return 0


def cmd_ocr(a):
    """Разобрать книгу: N проходов в `passes/`, готовый текст наверху.

    Одиночный прогон идёт по той же дороге, что и цепочка, — тоже в
    `passes/1`, тоже со сборкой.  Отдельного случая нет нарочно: пока он был,
    одиночный прогон давал другую раскладку, и всё, что читает разбор, обязано
    было знать про обе.
    """
    _open_log(a)
    return _multipass(a)


# Меньше этого остатка проход начинать бессмысленно: уйдёт на подключение и
# подъём модели, а считать будет нечего.
MIN_PASS_MIN = 4.0


def _multipass(a):
    """Несколько проходов подряд и свод в одну книгу с пометками.

    Первый проход жадный — он и станет основным разбором.  Остальные идут
    при ненулевой температуре и служат свидетелями: ячейка, прочитанная
    всеми одинаково, надёжна; разошедшаяся помечается `≠`.

    Проходы кладутся в отдельные каталоги-соседи, а не подкаталоги: у
    каждого свои вырезанные сканы таблиц, и набор выживших таблиц разный —
    свалив их вместе, мы получили бы одинаковые имена при разном
    содержимом.

    Второй и третий проходы идут на той же машине через --reuse: холодный
    старт стоит от полутора до пятнадцати минут, счёт — три.
    """
    import copy

    if a.dry_run:
        # Проверочный запуск: показываем, что сняли бы, и уходим.  Сводить
        # нечего — каталогов проходов не существует.
        print(f"проверочный запуск: сделал бы {a.passes} прохода "
              f"в {a.outdir}/passes/1..{a.passes} и собрал бы наверху")
        one = copy.copy(a)
        one.outdir = layout.pass_dir(os.path.abspath(a.outdir), 1)
        return _one_pass(one)

    base = os.path.abspath(a.outdir)
    dirs, iid = [], a.reuse
    # Бюджет и срок — на всю цепочку, а не на каждый проход.
    #
    # До этого каждый проход строил свой `Budget` от нуля, и `--passes 3
    # --timeout 90` означало не полтора часа, а четыре с половиной: три
    # независимых сторожа по 90 минут.  Денежный потолок так же умножался на
    # три.  Оператор, набравший «не больше доллара и не дольше часа»,
    # покупал три доллара и три часа — молча.
    chain_started = time.time()
    chain_deadline = chain_started + a.timeout * 60
    spent = 0.0
    truncated = False
    done = False
    def _drop_machine(why):
        """Погасить машину, оставленную ради следующего прохода.

        Промежуточные проходы идут с `--keep`, потому что следующий придёт на
        ту же машину.  Если следующего не будет — по исчерпанию предела, по
        ошибке прохода, по Ctrl-C, — гасить её некому: раньше это всегда делал
        последний проход, а теперь последнего может не случиться.  Замер
        показал цену: обрыв на втором проходе оставлял машину жить до дозора,
        и `--timeout 90 --budget 1.00` оборачивался 189 минутами биллинга.
        """
        if not iid:
            return
        if a.keep:
            # Оператор просил машину оставить — оставляем и при обрыве.  Иначе
            # `--keep` молча отменялся ровно там, где он нужнее всего: разобрать
            # упавший прогон и продолжить его `--resume` на прогретой машине,
            # не платя за холодный старт (от полутора до пятнадцати минут).
            log(f"инстанс {iid} ОСТАВЛЕН по --keep, хотя {why}. "
                f"Убить: books down {iid}")
            return
        try:
            Vast().destroy(int(iid))
            log(f"инстанс {iid} уничтожен: {why}")
        except Exception as e:
            log(f"не смог уничтожить инстанс {iid} ({e}) — "
                f"погаси сам: books down {iid}")

    try:
        for i in range(1, a.passes + 1):
            left_min = a.timeout - (time.time() - chain_started) / 60
            left_usd = a.budget - spent
            # Порог не в одну минуту: за минуту не успевает даже подключение к
            # машине и подъём сервера (замер: 11 с + 66 с на повторном проходе, и
            # от полутора до пятнадцати минут на холодном старте).  Проход, снятый
            # под полторы минуты счёта, — это оплаченный старт без результата.
            if left_min <= MIN_PASS_MIN or left_usd <= 0.02:
                print(f"цепочка исчерпала предел ({a.timeout} мин, ${a.budget:.2f}): "
                      f"осталось {left_min:.1f} мин и ${left_usd:.3f} — "
                      f"проход {i} не начинаю, свожу что есть")
                truncated = True
                break
            d = layout.pass_dir(base, i)
            one = copy.copy(a)
            one.outdir, one.reuse = d, iid
            one.timeout, one.budget = left_min, left_usd
            # Свидетелю картинки не нужны: свод читает у него только
            # страницы и книжный файл.  Первый проход — основа разбора, ему
            # нужно всё.
            #
            # Не `*.json`: в корне выходного каталога лежат run.json,
            # vllm.json и progress.json, по которым ведётся журнал прогонов и
            # подбирается машина.  Исключив их, мы бы молча ухудшили выбор
            # машины ради экономии килобайтов.
            one.pull_exclude = () if i == 1 else ("imgs/", "pages/*.json")
            # Последний проход тоже с --keep, если оператор просил: гасить машину
            # решает он, а не число проходов.
            one.keep = True if i < a.passes else a.keep
            if i > 1:
                os.environ["VLM_TEMPERATURE"] = str(a.temperature)
            report = {}
            log(f"=== проход {i} из {a.passes} -> {os.path.relpath(d)} "
                f"(цепочке осталось {left_min:.0f} мин, ${left_usd:.2f})")
            # Между проходами машина остаётся нарочно, но если наш процесс упадёт
            # в промежутке, гасить её будет только дозор мертвеца.  Его умолчание —
            # четыре часа, рассчитанные на «вернусь вечером»; здесь это означало бы
            # ночь оплаченного простоя.  Даём столько, сколько осталось цепочке,
            # плюс десять минут на пересменку.
            try:
                rc = _one_pass(one, report=report,
                               keep_until=chain_deadline if i < a.passes else None,
                               keep_usd=left_usd if i < a.passes else None)
            finally:
                # И на пути исключения тоже.  Проверка показала: если
                # `run_job` бросает (например «за N попыток не нашлось
                # машины»), строка ниже не выполняется, и `except
                # BaseException` гасит СТАРЫЙ номер, а живая машина,
                # снятая взамен умершей, остаётся брошенной.
                iid = report.get("instance_id") or iid
            # Отсутствие числа — не «денег не потрачено».  Если проход не сказал,
            # сколько стоил, считаем по цене машины и по времени: иначе денежная
            # половина ограничителя выключалась целиком и молча.
            cost = report.get("cost_usd")
            if cost is None:
                dph = float(report.get("dph") or a.max_dph)
                cost = dph * (time.time() - chain_started) / 3600 - spent
            spent += max(0.0, float(cost))
            # Номер машины забираем ДО проверки кода возврата и НЕ через
            # `iid or`.  Две денежные ошибки в одной строке, обе молчаливые:
            #
            # 1. Забирали после `return rc`, поэтому упавший ПЕРВЫЙ проход
            #    оставлял `iid` пустым, `_drop_machine` молча ничего не делал
            #    (он начинается с `if not iid: return`), а машина шла с
            #    `--keep` — то есть жила до дозора мертвеца, сжигая весь
            #    заявленный бюджет без единой страницы результата.  Заявка
            #    «гасится на всех путях обрыва» для первого прохода не
            #    выполнялась.  `report` заполняется в `finally`, так что номер
            #    там есть и при неуспехе.
            # 2. `iid or ...` не подхватывал НОВУЮ машину: если машина первого
            #    прохода умерла, `run_job` честно снимает другую, но `iid`
            #    оставался старым.  Дальше гасили несуществующую, следующий
            #    проход шёл с `--reuse` на мертвеца и снимал третью, а живая
            #    вторая оставалась брошенной и неучтённой.
            if rc != 0:
                print(f"проход {i} завершился с кодом {rc} — свод не делаю")
                _drop_machine(f"проход {i} завершился с кодом {rc}")
                return rc
            dirs.append(d)
    except BaseException:
        # Ctrl-C и любая иная беда: машина оставлена промежуточным проходом
        # ради следующего, которого уже не будет.
        _drop_machine("прогон прерван")
        raise
    if not dirs:
        _drop_machine("ни один проход не выполнен")
        raise SystemExit("ни один проход не выполнен")
    if truncated:
        _drop_machine("цепочка оборвана по пределу")
    os.environ.pop("VLM_TEMPERATURE", None)

    from . import merge
    layout.remember(base, source=os.path.basename(a.pdf),
                    stem=layout.clean_stem(a.pdf), passes=len(dirs),
                    cost_usd=round(spent, 4))
    rc = merge.assemble(base)
    rc = rc or _restructure_after(base)
    if truncated and not rc:
        # Усечённый свод не должен выглядеть выполненной работой: попросили N
        # проходов, сделали меньше, и свидетелей у книги меньше обещанного.
        # Книга при этом собрана и лежит на месте — об этом сказано рядом.
        print(f"ВНИМАНИЕ: просили {a.passes} прохода, выполнено {len(dirs)}. "
              f"Книга собрана в {base}, но свидетелей у неё меньше, чем "
              f"заказано, и пометок расхождения будет меньше.")
        return 2
    return rc


def _restructure_after(outdir):
    """Сборка структуры в конце прогона.

    Шагом руками её делать нельзя: забудется ровно один раз и молча — книга
    будет выглядеть готовой, а заголовков в ней не будет.  Ошибку здесь не
    поднимаем: разбор уже оплачен и лежит на диске, и терять его из-за
    неудавшейся расстановки заголовков незачем — шаг повторяем командой
    `books restructure`.
    """
    from . import structure
    try:
        return structure.restructure(outdir)
    except Exception as e:
        print(f"структура не собралась ({e}); разбор цел, "
              f"повторить: books restructure {outdir}")
        return 0


def _one_pass(a, report=None, keep_until=None, keep_usd=None):
    spec = paddleocr.spec(
        os.path.abspath(a.pdf), gpu=a.gpu, image=a.image, minutes=a.minutes,
        budget_usd=a.budget, disk_gb=a.disk, max_dph=a.max_dph,
        machine_id=a.machine, table_threshold=a.table_threshold)
    # Длинный прогон надо уметь продолжить: на 539 страницах падение на
    # четырёхсотой иначе означает полный пересчёт.  По умолчанию каталог с
    # результатом на машине чистится — иначе --reuse выдавал бы чужой
    # результат за свой.
    spec.resume = bool(getattr(a, "resume", False))
    spec.pull_exclude = tuple(getattr(a, "pull_exclude", ()) or ())
    spec.timeout_minutes = a.timeout
    if not os.path.exists(a.pdf):
        raise SystemExit(f"нет файла: {a.pdf}")
    rc = run_job(spec, a.outdir, ssh_key=config.ssh_key(a.ssh_key),
                 keep=a.keep, reuse=a.reuse, dry_run=a.dry_run,
                 report=report, keep_until=keep_until, keep_usd=keep_usd)
    # Промежуточные проходы свод разметит сам; структуру собираем один раз, в
    # конце, и только когда прогон был одиночным.
    if rc == 0 and not a.dry_run and report is None:
        rc = _restructure_after(a.outdir)
    return rc


def cmd_olmocr(a):
    """То же самое, но моделью olmOCR-2-7B.

    Отдельная команда, а не флаг у `ocr`: у задач разные веса, разное дерево
    пакетов и разное поведение при нехватке памяти, и общий код свёлся бы к
    ветвлению в каждой строке.
    """
    _open_log(a)
    spec = olmocr.spec(
        os.path.abspath(a.pdf), gpu=a.gpu, image=a.image, minutes=a.minutes,
        budget_usd=a.budget, disk_gb=a.disk, max_dph=a.max_dph,
        machine_id=a.machine, model_repo=a.model_repo,
        concurrency=a.concurrency)
    spec.timeout_minutes = a.timeout
    if not os.path.exists(a.pdf):
        raise SystemExit(f"нет файла: {a.pdf}")
    return run_job(spec, a.outdir, ssh_key=config.ssh_key(a.ssh_key),
                   keep=a.keep, reuse=a.reuse, dry_run=a.dry_run)


def cmd_convert(a):
    """Разбор -> EPUB и FB2 рядом с book.md."""
    from . import convert
    return convert.convert(a.outdir, formats=tuple(a.formats.split(",")),
                           title=a.title)


def cmd_restructure(a):
    """Собрать книжную структуру в готовом разборе.

    Шаг местный и без карты: он ничего не читает со скана, только раскладывает
    уже разобранное по меткам из `pages/*.json`.  Поэтому он и вынесен из
    задачи распознавателя — иначе поправить его можно было бы только новым
    платным прогоном.
    """
    from . import structure
    return structure.restructure(a.outdir)


def cmd_merge(a):
    """Собрать книгу из уже скачанных проходов, не арендуя карту.

    Свод был доступен только изнутри платного прогона, и это стоило книге
    проверки: сличение прозы дописали в `merge.py` позже, чем собрали обе
    книги, и обе остались сверенными только по ячейкам таблиц — ноль пометок
    `чтения разошлись` при живых каталогах проходов на диске.  Правку свода,
    которую нельзя применить к уже оплаченному разбору, применяют к нему
    никогда.

    Шаг местный, карта не нужна.  Ничего не сносит и не копирует: читает
    черновики проходов, пишет книгу и слепок.
    """
    from . import merge
    p = layout.Paths(a.outdir)
    if not p.new:
        raise SystemExit(
            f"нет {a.outdir}/passes — это не каталог книги. "
            f"Разбор старой раскладки переводится командой books tidy.")
    thin = [os.path.relpath(d) for d in p.passes
            if not glob.glob(os.path.join(d, "pages", "*.md"))]
    if thin:
        # Пустой `pages/` прежде проходил проверку на существование каталога, и
        # свод писал пустую книгу с кодом 0.  Считаем файлы, а не каталоги.
        raise SystemExit("в проходах нет ни одной страницы: " + ", ".join(thin))
    rc = merge.assemble(a.outdir)
    return rc or _restructure_after(a.outdir)


def cmd_tidy(a):
    """Перевести старый разбор в нынешнюю раскладку.

    Старая раскладка держала проходы каталогами-соседями (`<имя>-pass1..3`), а
    в самом `<имя>` лежала копия первого прохода — 177 МБ страниц и картинок
    на диске дважды.  Связь между каталогами держалась на совпадении имён, и
    ни один из них не сообщал, из какого pdf сделан.

    Шаг переносит проходы внутрь, выбрасывает копию и пересобирает книгу.
    Ничего не удаляется до того, как проходы окажутся на месте: сначала
    переезд, потом уборка, потом сборка.
    """
    from . import merge
    out = os.path.abspath(a.outdir)
    if not os.path.isdir(out):
        raise SystemExit(f"нет каталога {a.outdir}")
    if layout.assembled(out) and not a.force:
        print(f"{a.outdir} уже в нынешней раскладке "
              f"(проходов {len(layout.pass_dirs(out))})")
        return 0

    # 1. Проходы внутрь.  Соседи `<имя>-passN` — обычный случай; каталог,
    #    разобранный одним проходом, становится собственным проходом 1.
    moved = []
    sib = sorted(glob.glob(out + "-pass*"))
    if sib:
        for d in sib:
            m = re.search(r"-pass(\d+)$", d)
            if not m:
                continue
            dst = layout.pass_dir(out, int(m.group(1)))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(d, dst)
            moved.append(f"{os.path.basename(d)} -> passes/{m.group(1)}")
    elif os.path.isdir(os.path.join(out, "pages")):
        dst = layout.pass_dir(out, 1)
        os.makedirs(dst, exist_ok=True)
        for name in ("pages", "book", "job.log", "run.json", "logprobs.json",
                     "vllm.json", "progress.json"):
            src = os.path.join(out, name)
            if os.path.exists(src):
                shutil.move(src, os.path.join(dst, name))
        moved.append("сам каталог -> passes/1")
    if not moved:
        raise SystemExit(f"в {a.outdir} не нашлось ни проходов-соседей, "
                         f"ни собственного pages/ — переводить нечего")
    for m in moved:
        print(f"  {m}")

    # 2. Уборка копии.  Только теперь, когда проходы на месте: до этого
    #    удалять нечего и опасно.
    for name in ("pages", "book"):
        d = os.path.join(out, name)
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"  убрана копия первого прохода: {name}/")
    for f in glob.glob(os.path.join(out, "*.md")) + \
             glob.glob(os.path.join(out, "*.before-restructure")):
        os.unlink(f)
    # Служебные файлы прохода наверху — след того же копирования.  Если такой
    # же лежит в проходе, наверху он лишний; если не лежит — переносим, а не
    # выбрасываем: по ним ведётся журнал и разбирается лента этапов.
    first = layout.pass_dir(out, 1)
    for name in ("job.log", "vllm.log", "logprobs.json", "vllm.json",
                 "progress.json"):
        top = os.path.join(out, name)
        if not os.path.exists(top):
            continue
        if os.path.exists(os.path.join(first, name)):
            os.unlink(top)
        else:
            shutil.move(top, os.path.join(first, name))

    pdf = a.pdf or layout.facts(out).get("source")
    if not pdf:
        raise SystemExit(
            f"не знаю, из какого pdf сделан {a.outdir} — старый run.json "
            f"этого не записывал. Укажите: books tidy {a.outdir} --pdf <файл>")
    layout.remember(out, source=os.path.basename(pdf),
                    stem=layout.clean_stem(pdf),
                    passes=len(layout.pass_dirs(out)))
    print(f"  книга: {layout.stem(out)}")

    rc = merge.assemble(out)
    return rc or _restructure_after(out)


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


class _Tee:
    """Пишет и на экран, и в файл.

    Журнал прогона нужен дважды: живым — чтобы видеть, где сейчас счёт, — и
    потом, чтобы понять, почему вышло так.  До сих пор он существовал, только
    если оператор сам додумался перенаправить вывод; каталог `runs/` полон
    таких файлов с именами вроде `mv3-run.log`, то есть привычка была, а опоры
    под ней не было.
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


def _open_log(a):
    """Включить запись журнала, если попросили. Возвращает путь или None."""
    # Журнал пишется ВСЕГДА, если не запретили явно.  Ключ, который надо
    # помнить включить, — это ключ, который забудут: прогон Фейнмана так и
    # прошёл мимо `runs/`, и `books progress` показала вместо него трёхдневный
    # отладочный журнал, потому что он оказался там самым свежим.
    path = getattr(a, "log", "")
    if path is None:
        return None
    if path == "":            # `--log` без значения — имя по каталогу разбора
        path = os.path.join("runs", os.path.basename(a.outdir.rstrip("/"))
                            + ".log")
    tee = _Tee(path)
    sys.stdout = tee
    sys.stderr = tee
    log(f"журнал прогона: {path} (смотреть: books progress {path})")
    return path


# Этапы прогона: по какой строке начинается, по какой кончается, как назвать.
# Порядок важен — по нему лента и строится.
_STAGES = [
    ("выкачивание образа, старт контейнера",
     r"жду выкачивания образа", r"статус=running|ssh готов"),
    ("заливка входных файлов",
     r"заливаю входные файлы", r"запускаю задачу"),
    ("установка окружения (python, torch, веса)",
     r"=== разворачиваю окружение ===", r"=== окружение ===|поднимаю vLLM"),
    # Между отчётом об окружении и подъёмом сервера лежат проверки карты и
    # импортов — двенадцать секунд на каждом проходе.  В первой редакции ленты
    # они не попадали ни в один этап и потому были не видны вовсе: время шло,
    # а строки о нём не было.
    ("проверка карты и пакетов",
     r"=== окружение ===", r"=== поднимаю vLLM|поднимаю vLLM"),
    ("подъём модели vLLM",
     r"=== поднимаю vLLM", r"пайплайн готов|=== разбираю"),
    ("счёт страниц",
     r"=== разбираю ", r"посчитано \d+ страниц"),
    ("выкачивание результата",
     r"забираю результат", r"итого [\d.]+ мин|готово за [\d.]+ мин"),
]
_P_RENT = re.compile(r"снимаю #(\d+) за \$([\d.]+)/час")
_P_PASS = re.compile(r"=== проход (\d+) из (\d+)")
_P_DONE = re.compile(r"посчитано (\d+) страниц за (\d+)с \(([\d.]+) стр/с\)")
_P_PAGES = re.compile(r"\s(\d+) страниц, ([\d.]+) стр/с")
_P_TOTAL = re.compile(r"итого ([\d.]+) мин ≈ \$([\d.]+)")
_P_TIME = re.compile(r"\[(\d\d):(\d\d):(\d\d)\]")


def _hms(sec):
    sec %= 24 * 3600
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _dur(sec):
    return f"{sec / 60:.1f} мин" if sec >= 60 else f"{sec} с"


def _events(lines):
    """Строки журнала со временем, приведённым к нашим часам.

    Часы у нас и у арендованной машины разные, и в журнале они идут вперемешку:
    наши строки без отступа, машинные — с отступом.  Пока их не свести, лента
    выглядит бредом — этап «кончился» на три часа раньше, чем начался.
    Сдвиг берём один раз, по первой машинной строке и последней нашей перед
    ней: они пишутся почти одновременно, потому что вывод идёт потоком.
    """
    out, last_local, shift = [], None, None
    for l in lines:
        m = _P_TIME.search(l)
        if not m:
            # Строка без отметки времени всё равно может быть вехой (в старых
            # журналах «=== проход N из M» печатался обычным print).  Даём ей
            # последнее известное время, иначе лента теряет границы проходов.
            if last_local is not None and _P_PASS.search(l):
                out.append((last_local, l.strip()))
            continue
        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        remote = l[:1].isspace()
        if not remote:
            last_local = sec
        elif shift is None and last_local is not None:
            shift = last_local - sec
        if remote:
            sec += shift or 0
        out.append((sec, l.strip()))
    return out


def cmd_progress(a):
    """Ход прогона лентой: что когда началось, когда кончилось, сколько шло.

    Первая редакция печатала сводку — «проход 2 из 3, счёт закончен» — и это
    оказалось не тем: по сводке не видно, что сейчас делается и не встало ли
    оно.  Нужна лента ключевых этапов, а не итог.
    """
    path = a.path
    if not path:
        # Самый свежий ПРОГОН, а не самый свежий файл.  Прежде бралось
        # последнее по времени изменения, и лента показывала то отладочный
        # журнал недельной давности, то пустышку от проверочного запуска —
        # оба «свежее» настоящего прогона, потому что их трогали позже.
        # Журнал без единого этапа прогоном не считается.
        logs = sorted(glob.glob(os.path.join("runs", "*.log")),
                      key=os.path.getmtime, reverse=True)
        if not logs:
            raise SystemExit("в runs/ нет журналов; запускай с --log")
        skipped = []
        for cand in logs:
            head = open(cand, encoding="utf-8", errors="replace").read()
            if any(re.search(st[1], head, re.M) for st in _STAGES):
                path = cand
                break
            skipped.append(os.path.basename(cand))
        if not path:
            raise SystemExit(
                "ни в одном журнале runs/ нет этапов прогона "
                f"({len(logs)} шт.) — укажите путь явно")
        if skipped:
            print(f"пропущено журналов без этапов: {len(skipped)} "
                  f"({', '.join(skipped[:3])}{'…' if len(skipped) > 3 else ''})")
    if not os.path.exists(path):
        raise SystemExit(f"нет журнала: {path}")
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    ev = _events(lines)
    if not ev:
        raise SystemExit(f"в журнале нет отметок времени: {path}")

    now = time.localtime()
    now_sec = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    quiet = (time.time() - os.path.getmtime(path)) / 60
    live = quiet < 3

    print(f"журнал: {path}")
    if not live:
        print(f"прогон не идёт: последняя запись {_hms(ev[-1][0])}, "
              f"{quiet / 60:.1f} ч назад" if quiet > 90 else
              f"прогон не идёт: последняя запись {_hms(ev[-1][0])}, "
              f"{quiet:.0f} мин назад")

    rent = next((_P_RENT.search(t) for _, t in ev if _P_RENT.search(t)), None)
    if rent:
        print(f"машина #{rent.group(1)}, ${float(rent.group(2)):.3f}/час")

    # Границы проходов; всё, что до первого прохода, — общая подготовка.
    marks = [(i, _P_PASS.search(t)) for i, (_, t) in enumerate(ev)
             if _P_PASS.search(t)]
    chunks = []
    if marks:
        for n, (i, m) in enumerate(marks):
            end = marks[n + 1][0] if n + 1 < len(marks) else len(ev)
            chunks.append((f"проход {m.group(1)} из {m.group(2)}",
                           ev[i:end]))
        if marks[0][0]:
            chunks.insert(0, ("подготовка", ev[:marks[0][0]]))
    else:
        chunks = [("", ev)]

    for title, part in chunks:
        if title:
            print(f"\n{title}")
        for name, beg_re, end_re in _STAGES:
            b = next((s for s, t in part if re.search(beg_re, t)), None)
            if b is None:
                continue
            e = next((s for s, t in part
                      if s >= b and re.search(end_re, t)), None)
            if e is None:
                print(f"  {_hms(b)} → идёт {_dur(max(now_sec - b, 0))}"
                      f"   {name}")
            else:
                print(f"  {_hms(b)} → {_hms(e)}  {_dur(e - b):>9}   {name}")
        d = next((_P_DONE.search(t) for s, t in part if _P_DONE.search(t)),
                 None)
        if d:
            print(f"       {d.group(1)} страниц, {d.group(3)} стр/с")
        elif not live:
            pass
        else:
            g = [_P_PAGES.search(t) for s, t in part if _P_PAGES.search(t)]
            if g:
                print(f"       сейчас {g[-1].group(1)} страниц, "
                      f"{g[-1].group(2)} стр/с")

    tot = [_P_TOTAL.search(t) for _, t in ev if _P_TOTAL.search(t)]
    if tot:
        mins = sum(float(m.group(1)) for m in tot)
        usd = sum(float(m.group(2)) for m in tot)
        print(f"\nвсего по журналу: {mins:.1f} мин ≈ ${usd:.2f}")
    bad = [t for _, t in ev
           if re.search(r"Traceback|завершился с кодом|не удалось", t)]
    for x in bad[-3:]:
        print(f"  !! {x[:100]}")
    return 0


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
    p.add_argument("--table-threshold", type=float, default=None,
                   help="опустить порог детекции таблиц (класс 21); "
                        "таблицы без линеек проигрывают тексту по уверенности")
    p.add_argument("--ssh-key", default=None)
    p.add_argument("--keep", action="store_true",
                   help="оставить машину для --reuse (ДЕНЬГИ ПРОДОЛЖАЮТ ИДТИ)")
    p.add_argument("--reuse", type=int, metavar="ID",
                   help="считать на уже поднятой машине, без холодного старта")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log", nargs="?", const="", default="", metavar="PATH",
                   help="куда писать журнал прогона; по умолчанию "
                        "runs/<имя каталога>.log. Смотреть: books progress")
    p.add_argument("--no-log", dest="log", action="store_const", const=None,
                   help="не писать журнал прогона в файл")
    p.add_argument("--resume", action="store_true",
                   help="продолжить прерванный прогон на той же машине, "
                        "не стирая уже посчитанные страницы")
    p.add_argument("--passes", type=int, default=1, metavar="N",
                   help="прочитать книгу N раз и свести в одну с пометками: "
                        "первый проход жадный, остальные при температуре, "
                        "разошедшиеся ячейки помечаются знаком ≠")
    p.add_argument("--temperature", type=float, default=0.4,
                   help="температура VLM для проходов со второго (при --passes)")
    p.set_defaults(fn=cmd_ocr)

    p = sub.add_parser("olmocr", help="разобрать PDF моделью olmOCR-2-7B")
    p.add_argument("pdf")
    p.add_argument("outdir")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="ожидаемое время счёта, влияет на выбор оффера")
    p.add_argument("--budget", type=float, default=1.00,
                   help="жёсткий потолок в долларах; при достижении машина гибнет")
    p.add_argument("--timeout", type=float, default=90.0, help="потолок в минутах")
    p.add_argument("--model-repo", default=None,
                   help="веса: по умолчанию allenai/olmOCR-2-7B-1025 (bf16); "
                        "на 4090 можно ...-1025-FP8 — вдвое меньше памяти")
    p.add_argument("--concurrency", type=int, default=None,
                   help="страниц в полёте одновременно (по умолчанию 8)")
    p.add_argument("--ssh-key", default=None)
    p.add_argument("--keep", action="store_true",
                   help="оставить машину для --reuse (ДЕНЬГИ ПРОДОЛЖАЮТ ИДТИ)")
    p.add_argument("--reuse", type=int, metavar="ID",
                   help="считать на уже поднятой машине, без холодного старта")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log", nargs="?", const="", default="", metavar="PATH",
                   help="куда писать журнал прогона; по умолчанию "
                        "runs/<имя каталога>.log. Смотреть: books progress")
    p.add_argument("--no-log", dest="log", action="store_const", const=None,
                   help="не писать журнал прогона в файл")
    p.set_defaults(fn=cmd_olmocr)

    p = sub.add_parser("convert", help="собрать EPUB и FB2 из готового разбора")
    p.add_argument("outdir", help="каталог разбора, внутри которого лежит book/book.md")
    p.add_argument("--formats", default="html,epub,fb2",
                   help="через запятую: html, pdf, epub, fb2 "
                        "(по умолчанию html, epub и fb2; pdf требует weasyprint)")
    p.add_argument("--title", default=None, help="заголовок книги")
    p.set_defaults(fn=cmd_convert)

    p = sub.add_parser("restructure",
                       help="собрать заголовки, оглавление и отчёт в book.md")
    p.add_argument("outdir", help="каталог разбора (processed/<имя>)")
    p.set_defaults(fn=cmd_restructure)

    p = sub.add_parser("merge",
                       help="собрать книгу из скачанных проходов, без GPU")
    p.add_argument("outdir", help="каталог книги (processed/<имя>)")
    p.set_defaults(fn=cmd_merge)

    p = sub.add_parser("tidy",
                       help="перевести старый разбор в нынешнюю раскладку")
    p.add_argument("outdir", help="каталог разбора (processed/<имя>)")
    p.add_argument("--pdf", help="исходник, если старый run.json его не помнит")
    p.add_argument("--force", action="store_true",
                   help="пересобрать, даже если раскладка уже нынешняя")
    p.set_defaults(fn=cmd_tidy)

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

    p = sub.add_parser("progress",
                       help="где сейчас прогон: коротко, по его журналу")
    p.add_argument("path", nargs="?", default=None,
                   help="путь к журналу; без него берётся свежий из runs/")
    p.set_defaults(fn=cmd_progress)

    p = sub.add_parser("ledger", help="журнал прогонов и оценки по нему")
    p.set_defaults(fn=cmd_ledger)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
