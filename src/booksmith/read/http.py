"""Доставка вопроса по HTTP: любой OpenAI-совместимый адрес.

Один транспорт покрывает три случая, и это не совпадение, а причина выбрать
именно этот протокол:

    vLLM на арендованной карте   http://127.0.0.1:8118/v1  — тот же код, что дома
    чужой vLLM / LM Studio       http://хост:порт/v1
    облачное API с ключом        https://.../v1, ключ из `.env`

ОТСЮДА ГЛАВНОЕ СВОЙСТВО: аренда — НЕ третий транспорт. На боксе `run.sh`
поднимает vLLM на петле, и туда идёт ровно та же команда с тем же кодом.
Значит почти весь платный путь проверяется дома бесплатно — против подставного
сервера (`tests/support.py`), — и на карту уезжает уже проверенное. Прежний
второй уровень платил за отладку разбора аренду за арендой; один раз это
стоило тринадцати запусков и $0.52, из которых полезных два.

`urllib` из стандартной поставки, а не `requests` и не `openai`. Так уже
решено в проекте: `pyproject.toml` снял `requests` со словами «HTTP в живом
коде идёт через urllib». Клиент `openai` добавил бы зависимость ради
пятидесяти строк и ещё одно место, где прячется повтор запроса.

ПОВТОР РАЗРЕШЁН ТОЛЬКО ДО ОТВЕТА. Обрыв связи, таймаут, 5xx — повторяем:
ответа не было вовсе, и второй вопрос это тот же первый. Ответ 200
НЕ ПОВТОРЯЕТСЯ НИКОГДА, что бы в нём ни лежало: пустота, обрывок, чушь.
Переспрос после ответа — это починка модели, правило проекта его запрещает, и
здесь запрет выражен кодом, а не обещанием в комментарии.

КЛЮЧ НЕ ЕЗДИТ В СЛЕПОК. `VLM_API_KEY` читается через `config.env`, то есть из
`.env`, а не через реестр ручек: всё, что объявлено ручкой, попадает в
`run.json` значением, и секрет уехал бы в файл, который кладут в git. В
отпечатке стоит только факт его наличия и длина.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

from . import Ask, Said, Transport
from .. import config
from ..run import knobs

# Что считать картинкой. Список объявлен, потому что `data:`-строка обязана
# нести верный тип: сервер, получивший `image/png` на JPEG, отвечает 400, и
# разбираться в этом на арендованной карте дорого.
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


def _data_uri(path: str) -> tuple[str, int]:
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise ValueError(
            f"{path}: не знаю такого вида картинки. Знаю {sorted(MIME)}; "
            f"вырезки кладёт `doc/crop.py`, и это .png")
    raw = open(path, "rb").read()
    if not raw:
        raise ValueError(
            f"{path}: вырезка пуста (0 байт). Послать её значит получить "
            f"выдуманный ответ на пустое место — модель на пустом белом листе "
            f"выдаёт таблицы, пять разных за пять попыток.")
    return f"data:{MIME[ext]};base64," + base64.b64encode(raw).decode(), len(raw)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Редирект НЕ выполняется, а объявляется отказом.

    Замер, из-за которого этот класс существует: `urllib` идёт за 302 сам, и
    ответивший нам сервер уводит запрос куда велит. При этом заголовок
    `Authorization` едет ДАЛЬШЕ — то есть `VLM_API_KEY` уходит на адрес,
    который назвал не оператор; POST превращается в GET, картинка теряется, а
    выдумка чужого сервера возвращается с `finish="stop"` и записывается
    чтением. Слепок при этом называет НАШ адрес.

    Ходить за редиректом незачем: адрес модели задаёт оператор ручкой, и
    подмена его на лету — не удобство, а подмена прогона.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"перенаправление на {newurl}: не иду. Ключ и картинка уехали бы "
            f"на адрес, который назвал сервер, а не оператор", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _BadBody(Exception):
    """Ответ пришёл, а разобрать его нечем. НЕ отказ доставки."""


def _read_json(req, timeout):
    """Ответ сервера -> json. Разбор ОТДЕЛЁН от доставки нарочно.

    Битое тело при коде 200 — это ОТВЕТ, а не обрыв связи, и повторять его
    нельзя: правило «модель никто не чинит» запрещает второй вопрос по
    отвеченному. Прежде `json.loads` стоял внутри общего `try`, и
    `JSONDecodeError` попадал в ветку отказа доставки — замер: битое тело,
    пустое тело и оборванное тело давали ТРИ обращения к службе при
    `VLM_RETRIES=2`, то есть тройную оплату порождения ровно на том отказе,
    которого проект и боится (обрыв длинной таблицы).
    """
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise _BadBody(f"{type(e).__name__}: {e}; первые байты "
                       f"{raw[:120]!r}") from None


def _headers(key, post=False):
    h = {"Authorization": "Bearer " + key} if key else {}
    if post:
        h["Content-Type"] = "application/json"
    return h


class Http(Transport):
    """OpenAI-совместимый адрес. Всё, что знает про модель, — её имя."""

    name = "openai-chat"

    def __init__(self, server: str | None = None, model: str | None = None):
        self.server = (server or knobs.knob("VLM_ENDPOINT")).rstrip("/")
        self.model = model or knobs.knob("MODEL_NAME")
        self.timeout = float(knobs.knob("VLM_TIMEOUT_S"))
        self.retries = int(knobs.knob("VLM_RETRIES"))
        # Ключ — из `.env`, не из реестра: см. шапку.
        self.key = config.env("VLM_API_KEY")
        if not self.server:
            # SystemExit, а не ValueError: оператор должен увидеть СТРОКУ, а не
            # стек до `sys.exit(main())`. Остальной CLI на такие беды отвечает
            # именно так (`books html` при подменённом PDF, `parse_pages`).
            raise SystemExit(
                "VLM_ENDPOINT пуст: не задан адрес модели. Умолчания нет "
                "нарочно — молчаливый `localhost` заставил бы прогон стучаться "
                "в никуда и объявить это молчанием модели.")

    # ------------------------------------------------------------- договор --
    def fingerprint(self) -> dict:
        return {"транспорт": self.name, "адрес": self.server,
                "модель спрошена": self.model,
                "таймаут с": self.timeout, "повторов доставки": self.retries,
                # Сам ключ НЕ пишем: слепок кладут в git.
                "ключ": ("есть, %d знаков" % len(self.key)) if self.key
                        else "нет"}

    def knobs_read(self) -> tuple[str, ...]:
        return ("VLM_ENDPOINT", "MODEL_NAME", "VLM_TIMEOUT_S", "VLM_RETRIES")

    # -------------------------------------------------------------- запрос --
    def check(self, model: str | None = None) -> dict:
        """Чем именно отвечает этот адрес. Величины, а не «сервер жив».

        Ради чего: на первом уровне проверка здоровья `curl /v1/models`
        отвечала СИРОТОЙ прошлого прогона, державшей 60% видеопамяти, и
        скрипт считал, что поднял сервер сам. Тут спрашивается не «жив ли», а
        «КАК ТЕБЯ ЗОВУТ», и несовпадение имени роняет прогон до первого цента.

        ЧЕГО ЭТА ПРОВЕРКА НЕ УМЕЕТ, и молчать об этом нельзя: `vllm serve
        --served-model-name` заставляет сервер называться КАК ВЕЛЕНО, а не как
        весы на диске. Совпадение имени доказывает, что мы попали на свой
        сервер, и НЕ доказывает, что под ним лежат обещанные веса. Веса
        доказывает только отпечаток чтеца, снятый рядом с ними.
        """
        want = model or self.model
        try:
            d = _read_json(urllib.request.Request(
                self.server + "/models", headers=_headers(self.key)),
                self.timeout)
        except Exception as e:            # noqa: BLE001 — любой отказ равнозначен
            raise RuntimeError(
                f"адрес {self.server} не отвечает на /models: {e}. "
                f"Это отказ ДОСТАВКИ, а не молчание модели.") from e
        ids = [m.get("id") for m in (d.get("data") or [])]
        out = {"адрес": self.server, "модели на сервере": ids,
               "спрашиваем": want, "совпало": want in ids}
        if not out["совпало"]:
            raise RuntimeError(
                f"на {self.server} стоит {ids}, а спрашивать собираемся "
                f"{want!r}. Считать в таком виде значит записать в слепок имя "
                f"одной модели при ответах другой — уверенно и неверно.")
        return out

    def send(self, ask: Ask) -> Said:
        """Один вопрос. Отказ возвращается ЗНАЧЕНИЕМ, а не броском."""
        uri, nbytes = _data_uri(ask.image)
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": uri}},
                {"type": "text", "text": ask.prompt}]}],
            **ask.params,
        }
        t0 = time.time()
        last = None
        # Повторяем ТОЛЬКО отказ доставки, и только пока ответа не было.
        for attempt in range(max(1, self.retries + 1)):
            try:
                req = urllib.request.Request(
                    self.server + "/chat/completions", method="POST",
                    data=json.dumps(body).encode(),
                    headers=_headers(self.key, post=True))
                d = _read_json(req, self.timeout)
            except _BadBody as e:
                # ОТВЕТ БЫЛ. Повторять нельзя — возвращаем значением сразу.
                return Said(anchor=ask.anchor,
                            error=f"тело ответа не разобрано: {e}",
                            took_s=time.time() - t0,
                            meta={"попыток доставки": attempt + 1,
                                  "байт картинки": nbytes,
                                  "ответ был": True,
                                  "промт": ask.prompt, "вид обещан": ask.kind})
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:400]
                # `e.reason` обязателен: у отказа от редиректа тело пустое, и
                # без причины оператор видел бы голое «HTTP 302:».
                last = f"HTTP {e.code} {e.reason}: {text}".rstrip(": ")
                # 4xx — наша ошибка в запросе, повторять её бессмысленно и
                # платно. Повторяем только то, что бывает временным.
                if e.code < 500:
                    break
            except Exception as e:        # noqa: BLE001 — обрыв, таймаут, DNS
                last = f"{type(e).__name__}: {e}"
            else:
                if not d.get("choices"):
                    # Сервер ответил 200 и не дал выбора вовсе (так отвечают
                    # шлюзы, кладущие ошибку в тело). Это НЕ молчание модели:
                    # молчание — это пустая строка в `content`.
                    return Said(
                        anchor=ask.anchor,
                        error=f"200 без choices: {json.dumps(d)[:200]}",
                        took_s=time.time() - t0, raw=d,
                        meta={"попыток доставки": attempt + 1,
                              "байт картинки": nbytes, "ответ был": True,
                              "промт": ask.prompt, "вид обещан": ask.kind})
                ch = d["choices"][0]
                msg = ch.get("message") or {}
                usage = d.get("usage") or {}
                return Said(
                    anchor=ask.anchor,
                    # `content` берётся как есть. `None` из json остаётся
                    # `None`: «поля не было» и «пустая строка» — разные ответы.
                    text=msg.get("content"),
                    finish=ch.get("finish_reason"),
                    took_s=time.time() - t0,
                    tokens=usage.get("completion_tokens"),
                    raw=d,
                    meta={"попыток доставки": attempt + 1,
                          "байт картинки": nbytes,
                          "имя модели в ответе": d.get("model"),
                          "промт": ask.prompt, "вид обещан": ask.kind})
            if attempt + 1 < max(1, self.retries + 1):
                time.sleep(min(2.0 * (attempt + 1), 10.0))
        return Said(anchor=ask.anchor, error=last or "отказ без объяснения",
                    took_s=time.time() - t0,
                    meta={"попыток доставки": self.retries + 1,
                          "байт картинки": nbytes,
                          "промт": ask.prompt, "вид обещан": ask.kind})


def build() -> Transport:
    """Транспорт по реестру ручек. Пока он один; список объявлен, чтобы
    второй добавлялся строкой, а незнакомое имя падало вслух."""
    name = knobs.knob("VLM_TRANSPORT")
    if name != "http":
        raise SystemExit(
            f"VLM_TRANSPORT={name!r}: знаю только 'http'. Молчаливый откат на "
            f"него означал бы, что опечатка в имени транспорта считается "
            f"успешным прогоном.")
    return Http()
