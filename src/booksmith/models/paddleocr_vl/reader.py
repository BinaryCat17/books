"""PaddleOCR-VL 1.6 как ЧТЕЦ: какой промт на какой ярлык и каким видом ответ.

Здесь нет ни одного запроса и ни одного адреса — это свойство модели, а не
доставки (разрез объявлен в `read/__init__.py`). Файл целиком состоит из
объявлений, и каждое объявление либо взято из карточки модели, либо оплачено
замером; догадок здесь быть не должно.

ПРОМТЫ ВЗЯТЫ У ВЕНДОРА ПОБАЙТОВО, а не сочинены. Карточка модели и рецепт
vLLM называют шесть задач одними и теми же строками:

    "OCR:"  "Table Recognition:"  "Formula Recognition:"
    "Chart Recognition:"  "Spotting:"  "Seal Recognition:"

Системного сообщения нет, температура 0. Промт — это ВСЁ, чем можно управлять
ответом: попросить «формат такой-то» нечем, и потому вид содержимого решает
не просьба, а выбор задачи.

ПОЧЕМУ МАРШРУТЫ ОБЪЯВЛЕНЫ ПОИМЁННО, А НЕ ВЫВЕДЕНЫ ИЗ РАЗРЯДА. Разряд
(`policy.role`) отвечает на вопрос «вырезать или печатать», а не «что
спросить»: `display_formula` и `table` оба «артефакт», а промты у них разные,
и вид ответа разный. Словарь ярлыков к тому же СВОЙ у каждого детектора — 25
имён у PP-DocLayoutV2, 20 у plus-L, по 17 у обеих моделей docling, 11 у
DocLayNet, — и правило «чего не знаю, то спрошу как текст» молча повело бы
двадцать шестой класс новых весов не тем промтом. `Reader.cover()` роняет
прогон на незнакомом ярлыке ДО первого цента.

ЧЕГО НЕ СПРАШИВАЕМ, И ЭТО ЗАМЕР, А НЕ ОСТОРОЖНОСТЬ. `image`, `header_image`,
`footer_image` — чтение текста внутри рисунков ПРОВЕРЕНО И ОТВЕРГНУТО
(`docs/ocr-notes.md`): выноски `A` и `B` не прочитаны вовсе, на их месте
цифра `1`; на двух страницах модель выдала школьную панграмму `The quick brown
fox…`, целиком выдуманную по штриховому чертежу; на третьей сорвалась в цикл
`1.` `2.` … `100.`; итого +2100 слов мусора на двадцати страницах. Штриховой
чертёж для этой модели — шум, а молчать она не умеет.

ЧТО ОБЪЯВЛЕНО ОСТОРОЖНО И ЖДЁТ ЗАМЕРА. У `chart` и `seal` промты вендорские,
а ВИД ответа не мерен нами ни разу. Объявлен `text` — самый осторожный из
четырёх: `books text` сверит такой ответ ЗНАКАМИ, а книга покажет его
экранированным, то есть ошибка объявления недооценит модель, но не испортит
книгу выдуманной таблицей. Рядом с ответом всегда лежит ДОГАДКА о виде
(`read/run.py` нюхает ответ и кладёт её в наблюдённое сбоку), и её расхождение
с объявленным — именной счётчик. То есть первый же прогон скажет числом,
надо ли менять `text` на `otsl`; менять по догадке, не спросив стенд, — это
починка модели, и её здесь нет.
"""
import hashlib
import os

from ...read import Reader, Route
from ...run import knobs

# Побайтово из карточки модели. Двоеточие и пробел значимы.
OCR = "OCR:"
TABLE = "Table Recognition:"
FORMULA = "Formula Recognition:"
CHART = "Chart Recognition:"
SEAL = "Seal Recognition:"

# Почему молчим — по одной причине на ярлык, и все три про одно.
NO_PICTURE = ("чтение внутри рисунков проверено и отвергнуто: выноски не "
              "прочитаны, выдуманная панграмма на двух страницах, срыв в "
              "цикл на третьей, +2100 слов мусора на двадцати страницах")

# Маршруты по СЛОВАРЮ ДЕТЕКТОРА. Ключ верхнего уровня — имя политики, ровно
# как в `policy.POLICIES`: два словаря разошлись бы, и это в проекте уже
# случалось (реестр ручек против сборщика задания, 13 имён из 17).
_TEXT_V2 = ("abstract", "algorithm", "aside_text", "content", "doc_title",
            "figure_title", "footer", "footnote", "formula_number", "header",
            "number", "paragraph_title", "reference", "reference_content",
            "text", "vertical_text", "vision_footnote")
_TEXT_PLUS = ("abstract", "algorithm", "aside_text", "content", "doc_title",
              "figure_title", "footer", "footnote", "formula_number",
              "header", "number", "paragraph_title", "reference",
              "reference_content", "text")
_TEXT_DOCLING = ("caption", "checkbox_selected", "checkbox_unselected",
                 "document_index", "footnote", "form", "key_value_region",
                 "list_item", "page_footer", "page_header", "section_header",
                 "text", "title")
_TEXT_EGRET = ("Caption", "Checkbox-Selected", "Checkbox-Unselected",
               "Document Index", "Footnote", "Form", "Key-Value Region",
               "List-item", "Page-footer", "Page-header", "Section-header",
               "Text", "Title")
_TEXT_DOCLAYNET = ("Caption", "Footnote", "List-item", "Page-footer",
                   "Page-header", "Section-header", "Text", "Title")


def _routes(text_labels, table, formula, picture, extra=()):
    r = {lab: Route(OCR, "text") for lab in text_labels}
    for lab in table:
        r[lab] = Route(TABLE, "otsl")
    for lab in formula:
        r[lab] = Route(FORMULA, "latex")
    for lab in picture:
        r[lab] = Route("", why=NO_PICTURE)
    r.update(extra)
    return r


ROUTES = {
    "PP-DocLayoutV2": _routes(
        _TEXT_V2, ("table",), ("display_formula", "inline_formula"),
        ("image", "header_image", "footer_image"),
        extra={"chart": Route(CHART, "text"), "seal": Route(SEAL, "text")}),
    "PP-DocLayout_plus-L": _routes(
        _TEXT_PLUS, ("table",), ("formula",),
        ("image",),
        extra={"chart": Route(CHART, "text"), "seal": Route(SEAL, "text")}),
    "Docling": _routes(
        _TEXT_DOCLING, ("table",), ("formula",), ("picture",),
        # `code` у docling — листинг программы. Промта «Code Recognition:» у
        # модели нет; спрашиваем как текст, потому что листинг И ЕСТЬ знаки,
        # и вид `text` тут не осторожность, а существо.
        extra={"code": Route(OCR, "text")}),
    "Docling-egret": _routes(
        _TEXT_EGRET, ("Table",), ("Formula",), ("Picture",),
        extra={"Code": Route(OCR, "text")}),
    "DocLayNet": _routes(
        _TEXT_DOCLAYNET, ("Table",), ("Formula",), ("Picture",)),
}


def _weights() -> dict:
    """Что за веса лежат под моделью. Объявленная пустота, а не молчание.

    Ради чего это поле. `vllm serve --served-model-name` заставляет сервер
    называться КАК ВЕЛЕНО, а не как веса на диске: проверка транспорта
    (`/v1/models`) доказывает, что мы попали на СВОЙ сервер, и не доказывает,
    что под ним обещанные веса. Замер, из-за которого это написано:
    `provision.sh` качал `PaddlePaddle/PaddleOCR-VL`, а `MODEL_NAME` объявлял
    `PaddleOCR-VL-1.6-0.9B` — это РАЗНЫЕ веса, репозиторий 1.6 отдельный, — и
    прогон вышел бы успешным и неверным, а слепок назвал бы версию, которой
    не считал.

    Дома весов нет вовсе, и тогда здесь стоит причина, а не `null`.
    """
    d = knobs.knob("VL_MODEL_DIR")
    if not d or not os.path.isdir(d):
        return {"каталог": d or None,
                "почему пусто": "весов рядом нет: считает не эта машина, а та, "
                                "куда смотрит VLM_ENDPOINT"}
    out = {"каталог": d, "файлов": len(os.listdir(d))}
    # ОТКУДА ВЗЯТЫ ВЕСА — главное поле, и пишет его `provision.sh` рядом с
    # ними. Прежде здесь стоял только `sha256 config.json`, и докстринг звал
    # его единственным доказательством версии. Замер опроверг: у
    # `PaddleOCR-VL-1.6` и у старого `PaddleOCR-VL` этот файл СОВПАДАЕТ
    # ПОБАЙТОВО — 2059 байт, sha256 ce7f4565f8b1db78…, — то есть сторож не
    # ловил ровно тот прогон, ради которого писался («качаем одно, объявляем
    # другое»). Он ловил лишь «весов нет вовсе».
    src = os.path.join(d, "ОТКУДА.json")
    if os.path.exists(src):
        try:
            import json as _j
            out["репозиторий"] = _j.load(open(src, encoding="utf-8")).get(
                "репозиторий")
        except (ValueError, OSError) as e:
            out["репозиторий"] = None
            out["почему пусто"] = f"ОТКУДА.json не читается: {e}"
    else:
        out["репозиторий"] = None
        out["почему пусто"] = ("рядом с весами нет ОТКУДА.json — его пишет "
                               "provision.sh; значит веса положены не им, и "
                               "какие они, сказать нечем")
    # Хэшируем файл, который у двух репозиториев РАЗЛИЧАЕТСЯ, а не тот, что
    # совпадает. `config.json` оставлен рядом вторым числом — он про
    # архитектуру, и его совпадение само по себе величина.
    for name in ("tokenizer_config.json", "config.json"):
        f = os.path.join(d, name)
        out["sha256 " + name] = (
            hashlib.sha256(open(f, "rb").read()).hexdigest()
            if os.path.exists(f) else None)
    return out


class PaddleOcrVl(Reader):
    """Чтец PaddleOCR-VL. Знает промты и виды — и ничего больше."""

    name = "paddleocr-vl"

    def __init__(self, policy_name: str = "PP-DocLayoutV2"):
        if policy_name not in ROUTES:
            raise SystemExit(
                f"нет маршрутов под словарь ярлыков {policy_name!r}: знаю "
                f"{sorted(ROUTES)}. Спрашивать по чужому словарю значит вести "
                f"таблицу промтом текста и записать прозу чтением.")
        self.policy_name = policy_name

    def fingerprint(self) -> dict:
        r = self.routes()
        return {"чтец": self.name,
                "модель": knobs.knob("MODEL_NAME"),
                "словарь ярлыков": self.policy_name,
                "веса": _weights(),
                # Промты уезжают в слепок ЦЕЛИКОМ, а не числом: поле «промты»
                # реестра слепка пусто у всех сегодняшних прогонов, и это
                # первое, что его заполняет. Промт — единственное, чем здесь
                # управляют ответом, и не записать его значит не записать
                # прогон.
                "промты": {lab: rt.prompt for lab, rt in sorted(r.items())
                           if rt.asked()},
                "не спрашиваем": {lab: rt.why for lab, rt in sorted(r.items())
                                  if not rt.asked()},
                "виды": {lab: rt.kind for lab, rt in sorted(r.items())
                         if rt.asked()}}

    def knobs_read(self) -> tuple[str, ...]:
        return ("MODEL_NAME", "VL_MODEL_DIR")

    def routes(self) -> dict[str, Route]:
        return dict(ROUTES[self.policy_name])

    def pixels(self) -> tuple[int, int]:
        """Окно вырезки, объявленное самой моделью. Не наши числа.

        `min_pixels` = 112 896 и `max_pixels` = 1280 * 28 * 28 = 1 003 520 —
        из карточки PaddleOCR-VL. Ниже нижней её процессор растягивает вырезку
        интерполяцией (замер прежнего прогона: табличная вырезка при 144 dpi
        выходила 375 x 66 = 24 750 px, вчетверо ниже порога, и растягивалась),
        выше верхней — ужимает.
        """
        return (112896, 1280 * 28 * 28)
