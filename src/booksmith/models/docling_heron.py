"""Второй детектор контуров: docling heron (IBM), RT-DETRv2 на ResNet-50.

ЗАЧЕМ ВТОРАЯ МОДЕЛЬ, ЕСЛИ МЫ НЕ СОБИРАЕМСЯ МЕНЯТЬ ПЕРВУЮ. Стенд померил у
PP-DocLayoutV2 дефект: две таблицы, стоящие бок о бок, она сливает в одну
рамку — 0 разделённых из 3 страниц, при 100% на `image`, `chart` и `header`.
Отличить «беда архитектуры DETR с однозначным сопоставлением» от «беда
обучающей выборки, где таблиц 1.18% и почти все одиночные» нельзя, глядя на
одну модель. Нужна вторая, независимая: другая архитектура (RT-DETRv2 против
RT-DETR-L), другие данные (150 тыс. документов IBM против 30 тыс. Baidu),
другой вход (640 против 800).

ЧЕГО ЭТА МОДЕЛЬ НЕ УМЕЕТ, И ЭТО НАДО ЗНАТЬ ДО ЗАМЕРА:

* **Порядка чтения нет.** В конвейере docling его считают правилами, отдельно
  от модели. `Block.order` здесь — позиция в нашем списке, и это ЗНАЧЕНИЕ,
  честно объявленное в отпечатке, а не ранг модели. Метрику порядка по ней
  считать нельзя.
* **Класса `chart` нет вовсе** — графики уходят в `picture`. Наш `chart` ей
  нечем выразить, и это не её ошибка, а разница словарей.
* **Отдельного номера страницы нет** — он внутри `page_footer`.

Постобработки docling (`LayoutPostprocessor`: пороги по классам, три итерации
уточнения рамок, слияние вложенных) при `DOCLING_PIPELINE=off` здесь НЕТ НИ
СТРОКИ, и это умолчание. Мы зовём граф напрямую: правило проекта — что модель
отдала, то и меряется.

КОНВЕЙЕР DOCLING — РУЧКА, А НЕ УМОЛЧАНИЕ.

`DOCLING_PIPELINE=post|full` включает два класса ВЕНДОРА, вызванных как есть,
без единой нашей правки внутри:

* `docling.utils.layout_postprocessor.LayoutPostprocessor` — пороги ПО КЛАССАМ
  (их СЕМНАДЦАТЬ, и перечень тут был неполон: 0.5 у caption, footnote,
  formula, list_item, page_footer, page_header, picture, table, text; 0.45 у
  section_header, title, code, document_index, form, key_value_region,
  checkbox_selected, checkbox_unselected), разрешение налезаний по трём
  разрядам (regular/picture/wrapper, свои area_threshold и conf_threshold),
  гашение совпадающих пар при IoU > 0.8, `TITLE -> SECTION_HEADER` и уход
  рамок, попавших внутрь обёртки, В ДЕТИ этой обёртки. Пороги — первое дело
  конвейера, и у нас они НЕ СНИМАЮТ НИ ОДНОЙ РАМКИ: самый высокий из
  семнадцати ровно 0.5, столько же, сколько наш `LAYOUT_SCORE_THRESHOLD`, и
  рамка ниже к ним просто не доезжает (числа — при `_DoclingPipeline.apply`).
  Уход в дети — не потеря сам по себе, но и не мелочь: 734 рамки из 15689 на
  золотом стенде становятся детьми, и чтобы «схлопнул» не читалось как
  «выбросил», каждая пишется в meta страницы полем «дети» — ярлыком и рамкой,
  а не одним номером в чужой нумерации. ПОТЕРЯ ТУТ НЕ У ВСЕХ: из верхнего
  списка вендор снимает детей только у обёрток-таблиц и картинок, а у `form`
  и `key_value_region` ребёнок остаётся и наверху — meta называет и то и
  другое двумя разными числами.
* `docling.models.postprocessing.reading_order_rb.ReadingOrderPredictor`.

«rb» ЗНАЧИТ RULE-BASED, и это надо говорить вслух. Файл — 740 строк ПРАВИЛ над
рамками, ни одного веса. Порядка чтения heron не предсказывает ни с ручкой, ни
без неё; конвейер меняет НАШЕ правило сортировки (сверху вниз, слева направо)
на ИХ правило. Назвать это «моделью порядка чтения» — соврать, и соврать
метрике: `metrics._model_has_rank` решает по слову «наш» в поле meta «порядок
чтения», сверять ли порядок с истиной или печатать НЕ СВЕРЯЕТСЯ. Поэтому все
три наших ответа начинаются со слова «наш» — и с конвейером тоже. Цена
обратного известна: на hard36 семь стендов печатали проценты порядка по
истине, которая про порядок молчала вовсе.

Правило проекта «модель никто не чинит» этим НЕ нарушено, и ровно по двум
причинам, обе обязательные: код вендора зовётся без правок (мы не сливаем и не
двигаем рамок сами) и включается объявленной ручкой, а не молча. Заплатка —
это когда рамку правим МЫ.

Что это даёт и чем платится — числами, развёрнуто: `run/knobs.py`, ручка
`DOCLING_PIPELINE`. Коротко, на 600 страницах золотого стенда (`off` против
`full`): рамок 15689 -> 9867, пар дублей IoU>=0.9 4435 -> 19, запросов к VLM
23.0 -> 14.6 на страницу, лишних прыжков между колонками 2718 -> 471 ШТУК
(на все 600 страниц это 4.53 -> 0.79, а сегодняшняя `metrics.column_jumps`
делит на страницы, попавшие в счёт, и печатает 5.24 -> 1.06: штуки те же,
знаменатель разный — и потому здесь стоят штуки).

Платится не только чернилами, и это главное в абзаце. Чернилами: целых
объектов 1049 -> 1042 из 1230, вне всех рамок 24.6% -> 26.3%, ПОРВАННЫХ
127 -> 135. А по мерке, которая штрафует слияние, — втрое дороже: найдено
артефактов 694 -> 562, смысл цел 602 -> 500, СЛИЯНИЙ 366 -> 461. Слияние
`books fitness` по построению не штрафует, и оценивать конвейер одними
чернилами значило бы назвать цену в семь объектов вместо ста тридцати двух.
Ровно поэтому умолчание ручки — ВЫКЛЮЧЕНО, а основой книги назначен
PP-DocLayoutV2: у него ранг чтения свой, и слияний 375 против 461.

`post` ПОРЯДОК ТОЖЕ МЕНЯЕТ, и здесь стояло обратное. Постобработчик не только
прореживает: последним делом он сортирует список сам — `_sort_clusters(mode=
"id")`, — а ключ этой сортировки на наших входных данных вырождается в точные
`(верх, лево)`: первый его член `min(cell.index)` не работает, клеток у нас нет
вовсе (`skip_cell_assignment=True`). Замер на 13 страницах `bench/slovar`:
вывод `post` совпал с сортировкой по (t, l) на 13 страницах из 13, а с нашим
ключом `(round(y/20), x)` — на 3; не на своём месте 237 рамок на 10 страницах.
И это не бесплатно: лишних прыжков между колонками у порядка `post` 474, а у
тех же самых рамок, пересортированных нашим ключом, — 453. То есть `post`
порядок УХУДШАЕТ. Чинит его только `full` — 0.79 прыжка на страницу.

ОБА ЧИСЛА ЭТОГО АБЗАЦА СНЯТЫ НА КЛЮЧЕ `(round(y/20), x)`, КОТОРОГО ПРИ `off`
БОЛЬШЕ НЕТ. Правило сборки переехало в `booksmith/order.py` (раздел 20
`docs/contour-notes.md`), и при `off` действует объявленное `(y0, x0)` либо
правила docling — по ручке `ASSEMBLY_ORDER`. Корзинный ключ остался ровно в
одном месте и ровно для одной работы: НУМЕРАЦИЯ перед вендорским конвейером,
`Cluster.id`, по нему вендор сшивает детей с обёрткой. Числа `post` (474) это
не двигает — там сортирует вендор; число 453 стало историческим.
"""
import hashlib
import json
import os
import sys

from .base import Block, Page, Recognizer
# Разряд ярлыка — НАША политика и живёт в одном месте. Здесь она нужна ради
# одного числа: сколько артефактных рамок вендор увёл в дети ТЕКСТОВОЙ
# обёртки, то есть потерял для книги. Считать это «своим» списком классов
# значило бы завести второй словарь разрядов, а они в этом проекте уже
# расходились.
from .. import order
from .. import policy
from ..run import knobs

MODELS = os.path.expanduser("~/.paddlex/official_models")


class WeightsMissing(RuntimeError):
    pass


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- вендорский конвейер docling: перевод ярлыков ---------------------------

# Словарь egret и словарь heron — ОДИН И ТОТ ЖЕ набор из 17 классов docling,
# записанный в весах по-разному: heron снейк-кейсом (`page_header`), egret
# витринными именами (`Page-header`, `Document Index`, `Key-Value Region`).
# Перевод объявлен ПОИМЁННО, а не выведен правилом «в нижний регистр, дефис в
# подчёркивание»: правило молча приняло бы восемнадцатый класс новых весов и
# подсунуло бы его вендору под выдуманным именем — ровно та беда, от которой
# `read()` защищается словами «выдуманный ярлык хуже отказа». Ярлык, которого
# здесь нет, роняет прогон вслух — как в `policy.py`.
EGRET_TO_DOCLING = {
    "Caption": "caption",
    "Checkbox-Selected": "checkbox_selected",
    "Checkbox-Unselected": "checkbox_unselected",
    "Code": "code",
    "Document Index": "document_index",
    "Footnote": "footnote",
    "Form": "form",
    "Formula": "formula",
    "Key-Value Region": "key_value_region",
    "List-item": "list_item",
    "Page-footer": "page_footer",
    "Page-header": "page_header",
    "Picture": "picture",
    "Section-header": "section_header",
    "Table": "table",
    "Text": "text",
    "Title": "title",
}

# Что умеет ручка. `off` — рамки модели как есть; `post` — только
# постобработка (рамки меняются, порядок остаётся нашим); `full` — она же плюс
# правила порядка чтения. ДВА включающих значения, а не одно «вкл», потому что
# эффекты разные и их надо уметь развести: `post` двигает и схлопывает рамки
# (15643 -> 9817), `full` сверх того переставляет их местами, геометрии не
# трогая вовсе. Слитые в одно, они дали бы «стало лучше» без ответа на вопрос,
# от чего именно.
PIPELINE_MODES = ("off", "post", "full")

_PIP_INSTALL = ('pip install -e ".[docling]"  (docling-slim==2.123.1 и rtree; '
                'без torch, +54 МБ)')


class _DoclingPipeline:
    """Два вендорских класса docling над рамками нашего адаптера.

    Здесь НЕТ НИ ОДНОЙ НАШЕЙ ПРАВКИ ВНУТРИ ЧУЖОГО КОДА. Наше в этом файле
    ровно три вещи, и каждая молчаливо опасна, поэтому названа отдельно.

    1. НАЧАЛО ОТСЧЁТА. Наши рамки идут от ЛЕВОГО ВЕРХНЕГО угла (`base.py`), а
       правила порядка сравнивают элементы через `self.b > other.b`, то есть
       ждут отсчёта СНИЗУ. Подать наши координаты как есть — получить книгу,
       прочитанную снизу вверх, и НИ ОДНА метрика рамок этого не заметит:
       рамки-то те же. Перевод делает сам docling
       (`models/stages/reading_order/readingorder_model.py:69`), делаем и мы —
       `bbox.to_bottom_left_origin(высота страницы)`.
    2. ПЕРЕВОД ЯРЛЫКОВ (`EGRET_TO_DOCLING`), поимённый, и сверяется он СРАЗУ
       по всему словарю весов, а не по ярлыкам, которые встретились на
       странице. Разница в цене: непереводимый класс уронит прогон на нулевой
       странице, а не на четырёхсотой после двадцати минут счёта.
    3. КЛЕТОК ТЕКСТА У НАС НЕТ. Мы считаем по растру, а не по текстовому слою
       PDF, поэтому `skip_cell_assignment=True`: иначе постобработчик стал бы
       подгонять рамки под клетки, которых нет, — и это была бы уже не его
       работа, а наша выдумка его руками.

    НАРУЖУ ЯРЛЫК ВОЗВРАЩАЕТСЯ В НАПИСАНИИ АДАПТЕРА. `policy.py` знает словари
    `Docling` и `Docling-egret` порознь, и подмена написания уронила бы прогон
    egret на своём же стенде: `detect.py` зовёт `policy.check` по словарю
    модели. Перевод — только на вход вендору и обратно.
    """

    def __init__(self, mode: str, labels, adapter: str):
        if mode not in PIPELINE_MODES:
            raise SystemExit(f"DOCLING_PIPELINE={mode!r}: знаю только "
                             f"{PIPELINE_MODES}")
        self.mode = mode
        self.adapter = adapter
        # Ленивый импорт и внятный отказ. Без ручки адаптер обязан считать и
        # вовсе без пакета — вот почему импорт здесь, а не в шапке файла;
        # с ручкой и без пакета он обязан падать вслух и называть, что ставить.
        try:
            import docling
            from docling.datamodel.base_models import Cluster, Page as DlPage
            from docling.datamodel.pipeline_options import (
                BaseLayoutPostprocessorOptions)
            from docling.utils.layout_postprocessor import LayoutPostprocessor
            from docling.models.postprocessing.reading_order_rb import (
                PageElement as RoElement, ReadingOrderPredictor)
            from docling_core.types.doc import BoundingBox, DocItemLabel, Size
        except ImportError as e:
            raise SystemExit(
                f"DOCLING_PIPELINE={mode}, а пакета docling нет: {e}. "
                f"Поставить: {_PIP_INSTALL}. Либо DOCLING_PIPELINE=off — "
                f"тогда адаптер считает рамки модели как есть, и пакет не "
                f"нужен вовсе.") from None
        self._Cluster, self._DlPage = Cluster, DlPage
        self._BoundingBox, self._DocItemLabel, self._Size = (
            BoundingBox, DocItemLabel, Size)
        self._LayoutPostprocessor = LayoutPostprocessor
        self._RoElement = RoElement
        # Предсказатель порядка держится ОДИН на прогон: конструктор ставит два
        # своих числа (`dilated_page_element`, порог горизонтального
        # расширения 0.15), и заводить его заново на каждой странице значило бы
        # обещать, что они могут разъехаться.
        self._ro = ReadingOrderPredictor() if mode == "full" else None
        self.options = BaseLayoutPostprocessorOptions(skip_cell_assignment=True)

        # Перевод ярлыков ПРОВЕРЯЕТСЯ ЦЕЛИКОМ, СРАЗУ И ПО ТОМУ СЛОВАРЮ,
        # КОТОРЫЙ У НАС ДЕЙСТВИТЕЛЬНО СПРОСЯТ. Здесь стояла сверка с
        # `DocItemLabel`, а в нём 30 имён против семнадцати, которые знает
        # постобработчик (`LayoutPostprocessor.CONFIDENCE_THRESHOLDS`), и порог
        # он берёт из этого словаря БЕЗ УМОЛЧАНИЯ. Тринадцать имён проходили
        # молча — chart, paragraph, reference, handwritten_text, marker,
        # grading_scale, empty_value и шесть field_*, — а первая же страница
        # падала голым `KeyError <DocItemLabel.CHART>` уже после поднятия
        # графа. Воспроизведено: `_DoclingPipeline("post",
        # DEFAULT_LABELS+["chart"], "docling-heron")` строился МОЛЧА (18
        # ярлыков), падал на нулевой странице. `chart` — ровно тот класс,
        # который шапка этого файла называет главной разницей словарей.
        known = {lab.value for lab in
                 LayoutPostprocessor.CONFIDENCE_THRESHOLDS}
        self.to_docling = {lab: EGRET_TO_DOCLING.get(lab, lab) for lab in labels}
        bad = []
        for lab, name in self.to_docling.items():
            try:
                DocItemLabel(name)
            except ValueError:
                bad.append(f"{lab!r} (-> {name!r}: такого имени нет в словаре "
                           f"docling вовсе)")
                continue
            if name not in known:
                bad.append(f"{lab!r} (-> {name!r}: имя в словаре docling "
                           f"есть, а порога у постобработчика нет)")
        if bad:
            raise SystemExit(
                f"адаптер {adapter}: ярлыки {', '.join(bad)} постобработчику "
                f"docling несъедобны. Он знает {len(known)} классов — те, что "
                f"перечислены в LayoutPostprocessor.CONFIDENCE_THRESHOLDS, "
                f"— и порог берёт по ярлыку без умолчания, то есть на любом "
                f"другом падает KeyError на первой же странице. Перевод "
                f"объявляется ПОИМЁННО в EGRET_TO_DOCLING "
                f"(models/docling_heron.py): "
                f"правило «в нижний регистр» молча приняло бы новый класс "
                f"новых весов и подсунуло бы его вендору под выдуманным "
                f"именем.")
        self.back = {v: k for k, v in self.to_docling.items() if v != k}

        # sha256 ОБОИХ файлов: они и есть правила. Правка правила у вендора
        # сменит наши рамки и наш порядок молча, а версия пакета при этом может
        # и не двинуться (правка в ветке, локальный патч, `pip install -e`).
        self.files = {}
        for cls in (LayoutPostprocessor, ReadingOrderPredictor):
            path = sys.modules[cls.__module__].__file__
            self.files[os.path.basename(path)] = _sha256(path)
        self.version = getattr(docling, "__version__", None)

        # Счётчики прогона. Числа, а не «готово»: без них «конвейер включён»
        # неотличимо от «конвейер включён и ничего не сделал».
        #
        # «ПЕРЕСТАВЛЕНО» СЧИТАЕТСЯ ДВАЖДЫ, потому что переставляют ДВОЕ.
        # Здесь был один счётчик, и считался он ТОЛЬКО внутри ветки `full`, —
        # значит при `post` в meta каждой страницы, в журнал и в `run.json`
        # уезжал ноль от непроверки, напечатанный как ноль от замера. А
        # постобработчик рамки как раз пересортировывает, и на `bench/slovar`
        # не на своём месте оказывались 237 рамок из 531.
        self.pages = self.before = self.after = self.kids = 0
        self.displaced = 0           # итог: не на своём месте против нашего
        self.resorted = 0            # сортировка постобработчика: оба режима
        self.reordered = 0           # правила порядка чтения: только `full`
        self.arte_in_text = 0        # артефакт уехал в дети ТЕКСТОВОЙ обёртки
        self.arte_lost = 0           # ...и не остался в верхнем списке

    # Строка про порядок ОБЯЗАНА начинаться со слова «наш»: по нему
    # `metrics._model_has_rank` понимает, что ранга модели здесь нет, и не
    # печатает процент из ничего. Правило при этом названо поимённо — чтобы
    # «наш» не читалось как «сверху вниз», когда он уже не сверху вниз.
    ORDER_RULE = {
        # `post` ПОРЯДОК МЕНЯЕТ. Здесь стояло «сортирует по Cluster.id, то есть
        # по нашему же порядку», и эта неправда уезжала в meta КАЖДОЙ страницы,
        # в `run.json`, в `books html` и в `books score`.
        # `LayoutPostprocessor._sort_clusters(mode="id")` берёт ключ из
        # трёх членов: `min(cell.index) if cluster.cells else sys.maxsize`,
        # затем `bbox.t`, затем `bbox.l`. А `cluster.cells` у нас ПУСТЫ
        # ВСЕГДА — `skip_cell_assignment=True` ставим мы сами. Первый член
        # ключа вырождается в константу, и остаются точные `(верх, лево)` —
        # НЕ наши полосы `round(y/20)`.
        # Замер (13 страниц `bench/slovar`, heron): вывод `post` совпал с
        # сортировкой по (t, l) на 13 страницах из 13, с нашим ключом — на 3;
        # не на своём месте 237 рамок на 10 страницах. Цена видна метрикой без
        # истины: лишних прыжков между колонками 474 у порядка `post` против
        # 453 у тех же рамок, пересортированных нашим ключом.
        # Слово «наш» в начале строки ОБЯЗАНО остаться, и оно тут не про
        # правило: `metrics._model_has_rank` читает его как «ранга модели нет»
        # и потому не печатает процент порядка по истине из ничего.
        "post": "ours_only_in_the_sense_that_the_model_gave_no_rank: the rule "
                "is FOREIGN -- the docling postprocessor resorted the boxes "
                "by (top, left), exact coordinates, not by our round(y/20) "
                "bands",
        "full": "ours_by_choice_rules_are_doclings_reading_order_rb: RULE-BASED, "
                "740 lines of rules without a single weight, not a model",
    }

    def _label(self, raw):
        """Ярлык адаптера -> ярлык docling. Неизвестный — вслух, а не KeyError.

        Дотянуться сюда с чужим ярлыком можно только мимо `read()` (он держит
        индекс класса в границах словаря весов), но сообщение «KeyError:
        'Chart'» не сказало бы, ЧТО чинить, а чинится это одной строкой в
        `EGRET_TO_DOCLING`.
        """
        try:
            return self._DocItemLabel(self.to_docling[raw])
        except KeyError:
            raise RuntimeError(
                f"ярлык {raw!r} не из словаря весов {self.adapter}: перевода "
                f"в словарь docling для него нет. Объяви его в "
                f"EGRET_TO_DOCLING поимённо.") from None

    def apply(self, blocks, width, height, index):
        """Рамки адаптера -> рамки после вендора. Возвращает (блоки, meta)."""
        clusters = [
            self._Cluster(
                id=b.block_id, label=self._label(b.label),
                bbox=self._BoundingBox(l=b.box[0], t=b.box[1],
                                       r=b.box[2], b=b.box[3]),
                confidence=b.score, cells=[], children=[])
            for b in blocks]

        resorted = None
        if self.mode in ("post", "full"):
            page = self._DlPage(page_no=index)
            page.size = self._Size(width=float(width), height=float(height))
            # ПЕРВОЕ ДЕЛО ПОСТОБРАБОТЧИКА — ПОРОГИ ПО КЛАССАМ — У НАС МЁРТВОЕ,
            # и знать это надо, чтобы не приписывать ему чужую работу. Все
            # семнадцать вендорских порогов не выше 0.5, а наш отбор в
            # `read()` уже отрезал по `LAYOUT_SCORE_THRESHOLD`, и его
            # умолчание — те же 0.5. Замер (matematika + slovar, heron и
            # egret, четыре прогона `off`): рамок 1948, ниже своего
            # вендорского порога НОЛЬ, минимальная уверенность 0.50033 при
            # самом высоком вендорском пороге ровно 0.5. Шаг оживёт только при
            # `LAYOUT_SCORE_THRESHOLD` ниже 0.45 — тогда 0.45-е классы
            # (section_header, title, code, document_index, form,
            # key_value_region, checkbox_*) начнут терять рамки первыми.
            clusters = self._LayoutPostprocessor(
                page, clusters, self.options).postprocess()
            # СКОЛЬКО РАМОК ПЕРЕСОРТИРОВАЛ САМ ПОСТОБРАБОТЧИК. Считается в
            # ОБОИХ режимах, потому что сортирует он в обоих: `_sort_clusters`
            # без клеток вырождается в точные (верх, лево), а НАШ порядок —
            # это порядок номеров (`Cluster.id`). Сравнение идёт с ним, а не с
            # длиной списка: прореживание сдвигает всех, и мерить надо
            # перестановку выживших, а не их убыль.
            ids = [c.id for c in clusters]
            resorted = sum(1 for a, b in zip(ids, sorted(ids)) if a != b)

        # Правила порядка чтения при `post` НЕ ЗОВУТСЯ ВОВСЕ — значит их число
        # тут прочерк, а не ноль. Ноль от непроверки и ноль от замера — разные
        # нули, и прежде здесь печатался первый под видом второго.
        moved = 0 if self.mode == "full" else None
        if self.mode == "full" and clusters:
            size = self._Size(width=float(width), height=float(height))
            els = []
            for i, c in enumerate(clusters):
                bb = c.bbox.to_bottom_left_origin(float(height))
                els.append(self._RoElement(
                    cid=i, text="", page_no=index, page_size=size,
                    label=c.label, l=bb.l, r=bb.r, b=bb.b, t=bb.t,
                    coord_origin=bb.coord_origin))
            # ПОРЯДОК ЗАВИСИТ ОТ ВЕРСИИ ПИТОНА — беда не наша, но забота наша.
            # Нетранзитивных `sorted()` в `reading_order_rb.py` ДВА, и оба
            # сортируют `PageElement` одним и тем же `__lt__`: «перекрываются
            # по горизонтали — сравнивай по низу, иначе по левому краю».
            # Строка 535 — `_find_heads(sorted(head_page_elems))`, строка 556 —
            # `_sort_ud_maps(sorted(child_provs))`. Здесь была названа одна
            # 535, а разошлась на замере как раз 556. Для
            # непоследовательного сравнения ответ `sorted` зависит от того, в
            # каком порядке реализация сравнивает пары. Замер: те же 600
            # страниц, тот же docling 2.123.1, те же pydantic 2.13.5 и numpy
            # 2.5.2 — на python 3.12.3 и 3.13.13 порядок разошёлся на ТРЁХ
            # страницах из 600 (0001, 0129, 0482). Рамки при этом до последнего
            # знака те же, набор тот же — переставлены места, и ни одна метрика
            # рамок этого не увидит.
            # НА ДВУХ НАШИХ КНИГАХ БЕДЫ НЕ ВИДНО ВОВСЕ, и это замеренный ноль,
            # а не пропущенная проверка: подменив имя `sorted` в пространстве
            # имён вендорского модуля (сам код вендора не тронут) на 25
            # страницах slovar+matematika, получили 75 вызовов `_find_heads`
            # (7 списков от трёх элементов) против 684 вызовов `_sort_ud_maps`
            # (13 списков) — и нетранзитивных троек 0 и там, и там. То есть
            # ловить расхождение надо на стенде побольше, а не на этих двух.
            # Внутри одного питона повторяется побайтово (проверено тремя
            # прогонами). Версия питона уезжает в слепок
            # (`detect.py:_packages`) — значит, расхождение хотя бы видно.
            order = [e.cid for e in self._ro.predict_reading_order(els)]
            # Перестановка обязана быть перестановкой. Правила разводят
            # колонтитулы и тело по трём спискам и сшивают обратно; потеряйся
            # там элемент — рамка исчезла бы из книги молча, а число рамок
            # «после» выглядело бы просто чуть меньшим.
            if sorted(order) != list(range(len(clusters))):
                raise RuntimeError(
                    f"правила порядка docling вернули не перестановку на "
                    f"странице {index}: было {len(clusters)} рамок, "
                    f"вернулось {len(order)} номеров")
            moved = sum(1 for i, j in enumerate(order) if i != j)
            clusters = [clusters[i] for i in order]

        # СОВОКУПНОЕ СМЕЩЕНИЕ ПРОТИВ НАШЕГО ПОРЯДКА — одним числом и по
        # окончательному списку: сколько выживших рамок стоят НЕ там, куда их
        # поставила бы наша нумерация (`Cluster.id`, он же наш ключ
        # `(round(y/20), x)`). Оно и уезжает в `detect.py` полем «переставлено
        # рамок»: тот складывает его по страницам и печатает итогом, а разложат
        # смещение на причины два поля ниже.
        final_ids = [c.id for c in clusters]
        displaced = sum(1 for a, b in zip(final_ids, sorted(final_ids))
                        if a != b)
        # Кто ОСТАЛСЯ НАВЕРХУ. Уйти в дети и пропасть из книги — не одно и то
        # же, и разводит их только этот набор: вендор снимает детей с верхнего
        # списка лишь у обёрток-таблиц и картинок (`TABLE_TYPES`, `PICTURE`), а
        # у `form` и `key_value_region` ребёнок остаётся и наверху тоже.
        # Проверено подстановкой: `document_index <- formula` — наверху одна
        # рамка `document_index`, формулы нет вовсе; `key_value_region <-
        # formula` — наверху обе.
        top = set(final_ids)

        out, kids, arte_in_text, arte_lost = [], {}, 0, 0
        for i, c in enumerate(clusters):
            lab = self.back.get(c.label.value, c.label.value)
            # ДЕТИ ОПИСЫВАЮТСЯ САМИ СОБОЙ, А НЕ НОМЕРОМ В ЧУЖОЙ НУМЕРАЦИИ.
            # Здесь лежал `{i: [k.id, ...]}` — ключ послеконвейерный (позиция в
            # ЭТОМ списке), значения доконвейерные (`Cluster.id`), а имя поля
            # предупреждало только про вторую половину. Связать одно с другим
            # было нечем: сами рамки перенумерованы с нуля, доконвейерный номер
            # в них не хранится вовсе, и восстановить его можно было только
            # вторым прогоном с `DOCLING_PIPELINE=off`. Теперь ключ — позиция
            # обёртки в этом же списке (её видно рядом), а ребёнок несёт свой
            # ярлык и свою рамку, и номер его назван полем, а не догадкой.
            ch = [{"id_before_pipeline": int(k.id),
                   "label": self.back.get(k.label.value, k.label.value),
                   "box": [k.bbox.l, k.bbox.t, k.bbox.r, k.bbox.b]}
                  for k in c.children]
            if ch:
                kids[i] = ch
                # ПОТЕРЯ СТРУКТУРЫ — ОТДЕЛЬНЫМ ЧИСЛОМ, И ЧИСЕЛ ДВА. Первое:
                # артефакт (таблица, картинка, формула, код) уехал в дети
                # ТЕКСТОВОЙ обёртки — `document_index`, `form`,
                # `key_value_region`. Второе, строже: его при этом не стало и
                # в верхнем списке, то есть обёртка уедет текстом, а вырезать
                # артефакт из неё уже некому. Разводить их обязательно:
                # проверено подстановкой, что у `form` и `key_value_region`
                # ребёнок остаётся наверху (потери нет), а у `document_index`
                # — единственной ТЕКСТОВОЙ обёртки из TABLE_TYPES — пропадает
                # совсем. Разбор 734 детей золотого стенда ПО ОБЁРТКАМ:
                # picture 526, key_value_region 161, document_index 26,
                # table 21; артефактных рамок в текстовых обёртках среди них 6.
                # На выжимке `bench/hard36` (36 страниц, heron, post) это
                # число НОЛЬ, и ноль посчитанный: детей 60 — 49 в обёртках
                # `picture`, 11 в `key_value_region`; по ярлыкам text 40,
                # caption 10, section_header 9, formula 1, и единственный
                # артефакт (formula) уехал в обёртку-КАРТИНКУ, которую второй
                # уровень вырежет целиком.
                if policy.role(lab) == "text":
                    art = [k for k in ch
                           if policy.role(k["label"]) == "artifact"]
                    arte_in_text += len(art)
                    arte_lost += sum(1 for k in art
                                     if k["id_before_pipeline"] not in top)
            out.append(Block(
                block_id=i,
                box=(c.bbox.l, c.bbox.t, c.bbox.r, c.bbox.b),
                label=lab, score=c.confidence, order=i))

        self.pages += 1
        self.before += len(blocks)
        self.after += len(out)
        self.kids += sum(len(v) for v in kids.values())
        self.displaced += displaced
        self.resorted += resorted or 0
        self.reordered += moved or 0
        self.arte_in_text += arte_in_text
        self.arte_lost += arte_lost
        meta = {
            "mode": self.mode,
            "boxes_before": len(blocks),
            "boxes_after": len(out),
            "moved_to_children": sum(len(v) for v in kids.values()),
            # ТРИ ЧИСЛА ВМЕСТО ОДНОГО, И КАЖДОЕ ОТВЕЧАЕТ НА СВОЙ ВОПРОС.
            # Первое — итог: сколько рамок стоят не там, где стояли бы в нашем
            # порядке. Его читает `detect.py` и складывает по книге, поэтому
            # имя поля прежнее. Прежде оно считалось ТОЛЬКО внутри ветки
            # `full`, то есть при `post` было нулём по построению — нулём от
            # непроверки, напечатанным как ноль от замера.
            # Второе и третье называют ПРИЧИНЫ, но НЕ СКЛАДЫВАЮТСЯ в
            # первое и складываться не должны: они меряны на разных шагах —
            # сортировка постобработчика (в обоих режимах) на своём выходе,
            # правила порядка (только в `full`) на своём. На slovar это видно
            # числами: итог 354, сортировка 237, правила 372.
            # Прочерк в третьем при `post` — не ноль: правила там не звались
            # ни разу.
            "boxes_reordered": displaced,
            "reordered_by_postprocessor_sort": resorted,
            "reordered_by_order_rules": moved,
            # Ключ — позиция обёртки В ЭТОМ списке; у каждого ребёнка свой
            # доконвейерный номер назван полем внутри. Обе нумерации названы,
            # смешать их больше нечем.
            "children_by_box_index": kids,
            # Не «сколько схлопнулось», а сколько при этом ПОТЕРЯНО. Первое
            # число — артефакты, уехавшие в дети ТЕКСТОВОЙ обёртки; второе —
            # те из них, кого в верхнем списке уже нет вовсе, то есть прямая
            # потеря структуры: обёртка уедет текстом, а вырезать артефакт из
            # неё некому.
            "artifact_boxes_in_text_wrappers": arte_in_text,
            "of_those_lost_from_top_level": arte_lost,
        }
        return out, meta

    def fingerprint(self):
        return {
            "mode": self.mode,
            "what_is_it": ("код ВЕНДОРА, вызванный как есть, без единой нашей "
                        "правки внутри; reading_order_rb — rule-based, 740 "
                        "строк правил над рамками, ни одного веса"),
            "classes": ["docling.utils.layout_postprocessor.LayoutPostprocessor"]
                      + (["docling.models.postprocessing.reading_order_rb."
                          "ReadingOrderPredictor"] if self.mode == "full"
                         else []),
            "docling_version": self.version,
            "sha256_vendor_files": self.files,
            "postprocess_options": self.options.model_dump(mode="json"),
            "label_map_to_docling": self.to_docling,
            "label_outward": "в написании адаптера",
            "summary": {"page_count": self.pages, "boxes_before": self.before,
                     "boxes_after": self.after, "moved_to_children": self.kids,
                     "boxes_reordered": self.displaced,
                     "reordered_by_postprocessor_sort": self.resorted,
                     # Прочерк, а не ноль: при `post` правила порядка не
                     # звались ни разу.
                     "reordered_by_order_rules":
                         self.reordered if self.mode == "full" else None,
                     "artifact_boxes_in_text_wrappers":
                         self.arte_in_text,
                     "of_those_lost_from_top_level": self.arte_lost},
        }


class DoclingHeron(Recognizer):
    name = "docling-heron"
    policy_name = "Docling"

    def __init__(self, model_dir: str | None = None):
        import onnxruntime as ort

        self.dir = model_dir or os.path.join(MODELS, "docling-heron_onnx")
        self.onnx = os.path.join(self.dir, "model.onnx")
        cfg_path = os.path.join(self.dir, "config.json")
        pre_path = os.path.join(self.dir, "preprocessor_config.json")
        missing = [p for p in (self.onnx, cfg_path, pre_path)
                   if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"нет весов docling heron: {missing}. Скачать три файла из "
                f"huggingface.co/docling-project/docling-layout-heron-onnx "
                f"в {self.dir}")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        i2l = cfg.get("id2label") or {}
        # Словарь ярлыков ОБЯЗАН приехать из весов. У ONNX-сборки heron его в
        # config.json нет — тогда берём объявленный здесь список и падаем, если
        # модель вернёт индекс за его пределами: выдуманный ярлык хуже отказа.
        self.labels = ([i2l[str(i)] for i in range(len(i2l))] if i2l
                       else list(DEFAULT_LABELS))
        # Ручка читается ЗДЕСЬ И ОДИН РАЗ на прогон, а не на каждой странице:
        # `os.environ` живой, и прогон, у которого половина страниц посчитана
        # одним правилом, а половина другим, был бы неповторим, а `run.json`
        # назвал бы одно значение. Строится конвейер ДО сессии ONNX: отказ
        # «нет пакета docling» стоит миллисекунды, а поднятие графа — секунды,
        # и падать надо на дешёвом.
        self.pipeline = knobs.knob("DOCLING_PIPELINE")
        self._pipe = (None if self.pipeline == "off"
                      else _DoclingPipeline(self.pipeline, self.labels,
                                            self.name))
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        size = pre.get("size") or {}
        self.target_h = int(size.get("height", 640))
        self.target_w = int(size.get("width", 640))
        # ФИЛЬТР ПЕРЕВОДИТСЯ, А НЕ ПЕРЕДАЁТСЯ НОМЕРОМ. В весах `resample`
        # записан кодом PIL, а мы жмём через cv2, и номера у них РАЗНЫЕ:
        # PIL 2 это BILINEAR, а cv2 2 — INTER_CUBIC. Молча передав число, мы
        # ужимали страницу другим фильтром, чем ужимали при обучении, и
        # заметить это было нечем: рамки остаются правдоподобными.
        pil = int(pre.get("resample", 2))
        # PIL: 0 NEAREST, 1 LANCZOS, 2 BILINEAR, 3 BICUBIC, 4 BOX, 5 HAMMING
        # cv2: 0 NEAREST, 1 LINEAR, 2 CUBIC, 3 AREA, 4 LANCZOS4
        PIL_TO_CV2 = {0: 0, 1: 4, 2: 1, 3: 2, 4: 3, 5: 3}
        if pil not in PIL_TO_CV2:
            raise WeightsMissing(
                f"незнакомый код фильтра resample={pil} в препроцессоре: "
                f"подставить свой значило бы ужимать страницу не тем.")
        self.interp_pil = pil
        self.interp = PIL_TO_CV2[pil]
        self.do_pad = bool(pre.get("do_pad", False))
        if self.do_pad:
            raise WeightsMissing(
                "в препроцессоре do_pad: true, а мы жмём растр без подложки — "
                "рамки вышли бы смещёнными и правдоподобными сразу.")
        self.do_rescale = bool(pre.get("do_rescale", False))
        self.do_normalize = bool(pre.get("do_normalize", False))
        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        kinds = {i.name: i.type for i in self.sess.get_inputs()}
        self.uint8_input = "uint8" in kinds.get("images", "")

    def _our_order(self, kept, w, h, index):
        """Наш порядок сборки — и ТОЛЬКО там, где он вправду наш.

        ДВА РАЗНЫХ СЛУЧАЯ, И ПРЕЖДЕ ОНИ БЫЛИ ОДНИМ. При `DOCLING_PIPELINE=off`
        этот список и есть книга, значит порядок надо брать из `order.py` —
        общий на проект и объявленный ручкой `ASSEMBLY_ORDER`. При `post` и
        `full` порядок задаёт ВЕНДОР: постобработчик сортирует список сам
        (`_sort_clusters(mode="id")`), а `full` вдобавок зовёт правила чтения.
        Наша сортировка там — не порядок чтения, а НУМЕРАЦИЯ: номер рамки это
        `Cluster.id`, по нему вендор сшивает детей с обёрткой, и переставь мы
        порядок потом — «дети» указывали бы в пустоту.

        Поэтому при включённом конвейере ключ остаётся ПРЕЖНИМ, побайтово:
        `(round(y/20), x)`. Он корзинный и для порядка чтения негоден — но
        здесь от него нужна только устойчивая нумерация, а сменить его значило
        бы сдвинуть все числа разделов 18 и 19, которые сняты на нём. Менять
        замеренное заодно с починкой нельзя: тогда неизвестно, что из
        изменившегося чьё.
        """
        if self._pipe is not None:
            kept.sort(key=lambda t: (round(t[2][1] / 20), t[2][0]))
            return kept
        # Правило спрашивается ОДИН раз и передаётся дальше: две отдельные
        # `rule()` читали бы окружение дважды за страницу, и правка ручки
        # посреди прогона развела бы сторожа с сортировкой.
        which = order.rule()
        order.cover(self.labels, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept],
                                 w, h, index, self.labels, which)
        return [kept[i] for i in perm]

    def _run_pipeline(self, blocks, w, h, index):
        """Рамки модели -> рамки после вендора. Возвращает (блоки, meta).

        При `off` не делает ничего и возвращает наш прежний порядок — сверху
        вниз и слева направо. Строка про порядок отдаётся ОТСЮДА всегда, а не
        пишется в `read()` константой: константа пережила бы включение
        конвейера и соврала бы метрике, что порядок наш прежний, когда он уже
        чужой.

        Числа в журнал каждые десять страниц — той же частотой, что и у самой
        команды `books detect`. Печатается `print`-ом, а не её `log`: у
        адаптера нет доступа к журналу команды, а молчать нельзя — «конвейер
        включён» без чисел неотличимо от «включён и ничего не сделал».
        """
        if self._pipe is None:
            # Что СТОЯЛО ЗДЕСЬ И БЫЛО НЕВЕРНО: константа «наш, сверху вниз и
            # слева направо» при сортировке `(round(y/20), x)` — корзинами по
            # двадцать пикселей растра. Два разных правила под одним именем, и
            # заметить это можно было только чтением обоих мест сразу. Теперь
            # правило одно (`order.py`) и называется тем, чем является.
            return blocks, {"reading_order": order.WORDS[order.rule()]}
        blocks, m = self._pipe.apply(blocks, w, h, index)
        pp = self._pipe
        if pp.pages == 1 or pp.pages % 10 == 0:
            print(f"  [конвейер docling {pp.mode}] {pp.pages} стр.: рамок "
                  f"{pp.before} -> {pp.after}, в дети {pp.kids} (из них "
                  f"артефактов в текстовых обёртках {pp.arte_in_text}, "
                  f"пропало {pp.arte_lost}), "
                  f"не на своём месте {pp.displaced} (сортировка сдвинула "
                  f"{pp.resorted}, правила переставили "
                  + (str(pp.reordered) if pp.mode == "full"
                     else "— (не звались)") + ")")
        return blocks, {"reading_order": _DoclingPipeline.ORDER_RULE[pp.mode],
                        "docling_pipeline": m}

    def thresholds(self) -> dict[str, float]:
        """Порог по каждому классу. Родного `draw_threshold` у этой сборки нет,
        поэтому берём общую ручку — и объявляем это прямо, чтобы число не
        выглядело чужим умолчанием."""
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """Чем действующий порог отличается от родного порога весов.

        У этой сборки родного порога НЕТ: в `config.json` нет `draw_threshold`,
        а docling держит свои семнадцать порогов в коде конвейера, а не в
        весах. Поэтому сторож честно говорит, что сравнивать не с чем, —
        и это не то же самое, что «расхождения нет».
        """
        return [f"родного порога у весов нет; действует "
                f"LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"на все {len(self.labels)} классов"]

    def knobs_read(self) -> tuple[str, ...]:
        """Ручка здесь ОДНА, и это сверено grep-ом по файлу.

        `knobs.knob()` в `docling_heron.py` зовётся дважды и оба раза с
        `LAYOUT_SCORE_THRESHOLD` (`thresholds`, `threshold_drift`). Чего тут
        НЕТ и почему: каталог весов зашит в `__init__` (`docling-heron_onnx`
        рядом с `MODELS`), поэтому `LAYOUT_MODEL_DIR` и `LAYOUT_MODEL_NAME`
        сюда не доходят вовсе; `LAYOUT_TABLE_THRESHOLD` не читается ничем —
        класс `table` берёт тот же общий порог, что и остальные шестнадцать.
        До этого объявления слепок прогона heron называл все три величины, и
        `LAYOUT_MODEL_NAME` в нём стоял `PP-DocLayoutV2` — имя чужой модели.

        `DoclingEgret` наследует список не по лени: своих `knob()` в нём нет
        ни одного, порог он берёт тем же `self.thresholds()`, а конвейер —
        тем же `__init__`.

        Вторая ручка — `DOCLING_PIPELINE` — добавлена вместе с вендорским
        конвейером и читается в `__init__` (один раз на прогон). Не объявить
        её значило бы вернуть слепку ту самую болезнь, ради которой это поле
        заведено: `run.json` двух прогонов, отличающихся ВСЕМ — 15643 рамки
        против 9817 и чужое правило порядка вместо нашего, — стал бы
        неотличим, потому что величина, решившая разницу, в нём помечена «к
        этому прогону не относится».
        """
        return ("LAYOUT_SCORE_THRESHOLD", "DOCLING_PIPELINE")

    def label_map(self) -> dict[str, str]:
        """Ярлыки НЕ переводятся в словарь PP-DocLayoutV2.

        Свести `picture` к `image`, а `formula` к `display_formula` значило бы
        стереть разницу словарей: у docling нет `chart` вовсе, и после свода
        «график назван картинкой» стало бы неотличимо от «график найден».
        Сличение идёт слепо к ярлыку, а сами ярлыки хранятся как есть.
        """
        return {}

    def fingerprint(self) -> dict:
        # ИТОГ КОНВЕЙЕРА — ЧИСЛОМ И В ЖУРНАЛ, ровно один раз за прогон. Хука
        # «прогон окончен» у адаптера нет, а `detect.py` зовёт `fingerprint()`
        # четырежды: трижды ДО цикла страниц (счётчик пуст — печатать нечего) и
        # один раз ПОСЛЕ, перед записью `run.json`. Условие «страниц > 0» и
        # ставит эту строку в единственное правильное место. Без неё «конвейер
        # включён» пришлось бы читать из json, а величина, которую не видно в
        # журнале, не сверяется с ожидаемой — на чём проект уже терял вечера.
        if self._pipe is not None and self._pipe.pages:
            it = self._pipe.fingerprint()["summary"]
            share = (100.0 * it["boxes_after"] / it["boxes_before"]
                    if it["boxes_before"] else 0.0)
            rules = (str(it["reordered_by_order_rules"])
                       if self._pipe.mode == "full" else "— (не звались)")
            # `post` порядок МЕНЯЕТ: сортировка постобработчика идёт по точным
            # (верх, лево), а не по нашему ключу round(y/20).
            order = ("ПРАВИЛА ВЕНДОРА (reading_order_rb, не модель)"
                       if self._pipe.mode == "full" else
                       "пересортирован постобработчиком docling по "
                       "(верх, лево), ранга модели нет")
            print(f"конвейер docling {self._pipe.mode}: страниц "
                  f"{it['page_count']}, рамок {it['boxes_before']} -> "
                  f"{it['boxes_after']} ({share:.1f}%), ушло в дети "
                  f"{it['moved_to_children']}, из них артефактов в текстовых "
                  f"обёртках {it['artifact_boxes_in_text_wrappers']} "
                  f"(пропало из верхнего списка "
                  f"{it['of_those_lost_from_top_level']}); "
                  f"не на своём месте против нашего порядка "
                  f"{it['boxes_reordered']} (сортировка постобработчика "
                  f"сдвинула "
                  f"{it['reordered_by_postprocessor_sort']}, правила "
                  f"переставили {rules}); порядок чтения {order}")
        return {
            "name": self.name,
            "model": getattr(self, "полное_имя",
                              "docling-layout-heron (RT-DETRv2 R50)"),
            "architecture": getattr(self, "architecture", "RT-DETRv2 R50"),
            "weights_dir": self.dir,
            "sha256_weights": _sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.target_h, "width": self.target_w,
                     "pil_filter": self.interp_pil,
                     "cv2_filter": self.interp, "padding": self.do_pad,
                     "input_uint8": self.uint8_input,
                     "divide_by_255": self.do_rescale,
                     "normalization": self.do_normalize},
            # Родного порога у сборки нет — это ЗНАЧЕНИЕ, а не пропуск.
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            # Не пустой список: сторож `threshold_drift` говорит, что родного
            # порога у сборки НЕТ и действует наш. Пустое поле рядом с ним
            # читалось как «расхождения нет», то есть слепок противоречил
            # собственному сторожу.
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            # Порядка чтения модель не даёт вовсе. Объявлено значением, чтобы
            # «порядок 100%» по ней нельзя было принять за заслугу модели.
            "reading_order": None,
            # Конвейер вендора назван и при `off` — ЗНАЧЕНИЕМ, а не пропуском.
            # Пустое место читалось бы как «не смотрели», а это «смотрели и
            # выключено»: без этой записи два прогона с разницей в 5826 рамок
            # различались бы в слепке одной строкой в реестре ручек.
            "docling_pipeline": (self._pipe.fingerprint() if self._pipe else {
                "mode": "off",
                "what_is_it": ("вендорская постобработка и правила порядка "
                            "чтения docling; выключены — рамки модели идут "
                            "как есть, порядок наш"),
                "docling_version": None,
                "sha256_vendor_files": {},
                "postprocess_options": None,
                "label_map_to_docling": {},
                "summary": None}),
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"не читается растр страницы: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1]                     # BGR -> RGB
        if self.uint8_input:
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None].astype(np.uint8))
        else:
            x = x.astype(np.float32)
            if self.do_rescale:
                x /= 255.0
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        labels, boxes, scores = self.sess.run(
            None, {"images": x,
                   # (ШИРИНА, ВЫСОТА), а не наоборот. Проверено на листе
                   # 1012x1466: при обратном порядке колонтитул уезжал на
                   # x=1269, то есть за правый край листа, — и метрика честно
                   # дала ноль совпадений из ста десяти. Ноль был про наш
                   # порядок осей, а не про модель.
                   "orig_target_sizes": np.array([[w, h]], np.int64)})
        labels, boxes, scores = labels[0], boxes[0], scores[0]

        thr = self.thresholds()
        kept, rejected = [], {}
        for cid, box, sc in zip(labels, boxes, scores):
            cid, sc = int(cid), float(sc)
            if not 0 <= cid < len(self.labels):
                raise RuntimeError(
                    f"модель вернула класс {cid}, а словарь знает "
                    f"{len(self.labels)}: выдуманный ярлык хуже отказа.")
            lab = self.labels[cid]
            if sc < thr[lab]:
                if sc > rejected.get(lab, 0.0):
                    rejected[lab] = sc
                continue
            kept.append((lab, sc, [float(v) for v in box]))
        # Порядка модель не даёт — значит он наш, и живёт он в `order.py`.
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=sc, order=i)
                  for i, (lab, sc, b) in enumerate(kept)]
        # Конвейер идёт ПОСЛЕ нашей сортировки и нумерации, а не до: номер
        # рамки — это `Cluster.id`, по нему вендор сшивает детей с обёрткой, и
        # переставь мы порядок потом — «дети» указывали бы в пустоту.
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            raw={"output_rows": int(len(scores)),
                 "all_rows": [[float(c), float(s), *[float(v) for v in b]]
                                for c, b, s in zip(labels, boxes, scores)]},
            meta={"detector": self.name, "raster": image_path,
                  # Это число — МОДЕЛИ: сколько рамок она отдала выше порога.
                  # Сколько их осталось после вендора, говорит «конвейер
                  # docling» -> «рамок после», и путать их нельзя.
                  "boxes_accepted": len(kept),
                  "rank_ties": 0,
                  # МЕСТО В СЛОВАРЕ НЕ КОСМЕТИКА: `порядок чтения` стоит там
                  # же, где стоял до конвейера, и при `off` страница выходит
                  # ПОБАЙТОВО той же, что и раньше. Иначе сверка «ручка
                  # выключена — ничего не изменилось» спотыкалась бы о
                  # порядок ключей json, а не о рамки.
                  **pipe_meta,
                  "best_rejected_by_class": rejected})


DEFAULT_LABELS = (
    "caption", "footnote", "formula", "list_item", "page_footer",
    "page_header", "picture", "section_header", "table", "text", "title",
    "document_index", "code", "checkbox_selected", "checkbox_unselected",
    "form", "key_value_region")


class DoclingEgret(DoclingHeron):
    """docling egret-medium: **D-FINE**, третья архитектура на стенде.

    Отличие от heron не в весах, а в ВЫХОДЕ: этот граф отдаёт СЫРЫЕ логиты и
    рамки в нормированных cxcywh, а не готовые тройки. Разбор логитов — часть
    инференса самой D-FINE (сигмоида, отбор лучших запросов, перевод в углы),
    а не наша постобработка: мы не двигаем и не сливаем рамок, а лишь читаем
    то, что граф не дочитал сам.
    """
    name = "docling-egret"
    policy_name = "Docling-egret"
    architecture = "D-FINE"

    def __init__(self, model_dir: str | None = None):
        self.full_name = "docling-layout-egret-medium (D-FINE)"
        super().__init__(model_dir or os.path.join(MODELS, "docling-egret_onnx"))
        names = [i.name for i in self.sess.get_inputs()]
        if names != ["pixel_values"]:
            raise WeightsMissing(
                f"вход графа {names}, а ждали ['pixel_values']: разбирать "
                f"наугад значит кормить модель не тем.")

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"не читается растр страницы: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1].astype(np.float32)
        if self.do_rescale:
            x /= 255.0
        x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        logits, boxes = self.sess.run(None, {"pixel_values": x})
        logits, boxes = logits[0], boxes[0]          # [Q, C], [Q, 4] cxcywh
        prob = 1.0 / (1.0 + np.exp(-logits))          # focal loss -> сигмоида
        nq, nc = prob.shape
        if nc != len(self.labels):
            raise RuntimeError(
                f"граф отдал {nc} классов, а словарь знает "
                f"{len(self.labels)}: выдуманный ярлык хуже отказа.")
        # ОТБОР ИДЁТ ПО ПРАВИЛУ САМОЙ D-FINE, А НЕ ПО НАШЕМУ argmax.
        # Прежде здесь стоял argmax по классам — «один запрос, один ярлык».
        # Так себя не дочитывает ни одна модель семейства DETR: сигмоида,
        # topk по РАЗВЁРНУТЫМ Q*C, ярлык = i % C, запрос = i // C. Тот же
        # кусок дословно лежит в постобработке RT-DETR и PP-DocLayoutV2
        # (`num_top_queries = logits.shape[1]`), а граф heron дочитывает себя
        # сам ровно им: 300 строк на страницу, одна и та же рамка приходит с
        # несколькими ярлыками — до 14 на atlas[0]; повтора КЛАССА внутри
        # одной рамки нет ни разу (0 групп из 13964), то есть группа — это
        # один запрос, а не две находки.
        # ЧЕМ РАСХОДИЛИСЬ ПРАВИЛА. На сыром выводе heron, где обе развязки
        # считаются по одним и тем же строкам: правило графа 1797 рамок,
        # argmax 1488, расходятся 22 страницы из 93. На egret по 24 страницам
        # шести стендов при пороге 0.5: argmax 470 рамок, правило D-FINE 529,
        # расходятся 6 страниц; все 59 добавленных — ВТОРОЙ ярлык на уже
        # принятой рамке (54 из них List-item рядом с Text), новой геометрии
        # не появляется ни одной. Пока правила были разные, сравнение heron с
        # egret меряло наши разборы наравне с архитектурами.
        # Длина topk НЕ наша ручка и не порог: это Q — столько строк отдал бы
        # сам граф, будь он экспортирован вместе с постобработкой (в весах
        # это `num_queries = 300`).
        flat = prob.reshape(-1)
        top = np.argsort(-flat, kind="stable")[:nq]

        thr = self.thresholds()
        # Сколько строк ВЫШЕ СВОЕГО ПОРОГА отрезал сам topk. Отрез — часть
        # правила модели, а не наша поправка, но молчать о нём нельзя:
        # правило D-FINE не только добавляет ярлыки, оно и режет, чего у
        # argmax быть не могло. LAYOUT_SCORE_THRESHOLD — ручка, и когда её
        # опускают, отрез начинает кусаться. Замер на 24 страницах шести
        # стендов: при 0.5 и 0.3 отрезано НОЛЬ (300-е значение развёртки не
        # поднимается выше 0.142), при 0.1 — 206 строк на katalog[2], где
        # страница упирается ровно в потолок: принято 300 = длине topk.
        # «Добавочных ярлыков» об этой потере не говорит ничего. Ноль здесь
        # считается на КАЖДОЙ странице и означает «topk ничего не отрезал».
        thr_row = np.array([thr[lab] for lab in self.labels], np.float32)
        inside = np.zeros(nq * nc, bool)
        inside[top] = True
        cut = int(((prob >= thr_row[None, :]).reshape(-1) & ~inside).sum())

        kept, rejected = [], {}
        for idx in top:
            q, cid = int(idx) // nc, int(idx) % nc
            s = float(flat[idx])
            lab = self.labels[cid]
            if s < thr[lab]:
                if s > rejected.get(lab, 0.0):
                    rejected[lab] = s
                continue
            cx, cy, bw, bh = (float(v) for v in boxes[q])
            kept.append((lab, s, [(cx - bw / 2) * w, (cy - bh / 2) * h,
                                  (cx + bw / 2) * w, (cy + bh / 2) * h]))
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        # Совпадающая геометрия считается ДО конвейера — это свойство ответа
        # модели, а гасит такие пары как раз вендор (IoU > 0.8). Считай мы её
        # после, число говорило бы о постобработке, а называлось бы правилом
        # отбора D-FINE.
        geom = [tuple(b) for _, _, b in kept]
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # Ответ графа ЦЕЛИКОМ, до нашего отбора. Хранить один класс и одну
            # сигмоиду на запрос значило бы положить в улику уже разобранное:
            # опустить порог по одному классу нельзя, не зная его сигмоиды у
            # запросов, где выиграл сосед. Замер на katalog[1]: развёртка
            # порога до 0.3 по прежнему raw давала 11 рамок из 14, до 0.2 —
            # 17 из 21; три и четыре рамки были не «ниже порога», а невидимы
            # по построению улики.
            raw={"output_rows": int(nq),
                 "class_count": int(nc),
                 "logits": [[float(v) for v in r] for r in logits],
                 "boxes": [[float(v) for v in r] for r in boxes],
                 "how_to_read_logits": "сигмоида поканально (focal loss)",
                 "raw_row_coords": "cxcywh, нормированные"},
            meta={"detector": self.name, "raster": image_path,
                  "boxes_accepted": len(kept), "rank_ties": 0,
                  # См. heron: место ключа держит побайтовое совпадение при
                  # выключенной ручке.
                  **pipe_meta,
                  # Правило отбора — величиной, а не словом, и рядом число, по
                  # которому видно, что оно и вправду работало: у прежнего
                  # argmax добавочных ярлыков не бывает по построению, так что
                  # ноль здесь означает «на этой странице правила совпали», а
                  # не «правило не применилось».
                  "selection_rule": f"topk {nq} по развёрнутым Q*C, "
                                    f"ярлык = i % {nc} (как в D-FINE/RT-DETR)",
                  "extra_labels_on_shared_boxes":
                      len(geom) - len(set(geom)),
                  "rows_above_threshold_outside_topk": cut,
                  # ОСТОРОЖНО: это поле сменило смысл вместе с правилом. Было
                  # «лучшее отвергнутое среди победителей argmax», стало
                  # «лучшее отвергнутое среди строк topk». Отсутствие класса
                  # в словаре читается «не попал в topk», а НЕ «такого класса
                  # у модели нет». Охват от смены вырос: было 4-8 классов на
                  # страницу, стало 4-16 (24 страницы шести стендов, 0.5).
                  "best_rejected_by_class": rejected})

