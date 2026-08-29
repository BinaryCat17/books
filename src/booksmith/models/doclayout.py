"""Детектор макета как самостоятельный распознаватель контуров.

Это ПЕРВАЯ ПОЛОВИНА первого уровня: рамки, ярлыки и порядок чтения, без
единого обращения к VLM.  Гоняется местно, на процессоре, бесплатно — вес
модели 214 МБ, страница считается пару секунд.  Тем и ценен: метрику контуров
можно проверять на настоящем выводе настоящей модели, не арендуя карту.

ПОЧЕМУ МИМО ПАЙПЛАЙНА PADDLEX.  Не из любви к низкому уровню — по замеру.
Постобработка пайплайна **стирает порядок чтения у всего, что мы собираемся
вырезать**: на 539 страницах одной книги `block_order` равен `null` у 683 из
683 блоков `image`, 695 из 695 `figure_title`, 584 из 584 `table`, 534 из 534
`number` — и у 0 из 6431 `text`.  Сырой выход даёт ранг ВСЕМ рамкам: 1254 из
1254 на 65 страницах `bench/`.  Порядок есть, его выбрасывают выборочно.

Она же удаляет рамки: по шести книгам (3268 страниц) `image` 2660 -> 1872,
`inline_formula` 15541 -> 14.  Геометрию при этом почти не трогает — рамки
совпадают с детекторными побайтово, — то есть ступени отбирают, а не
переформовывают.

ЧЕГО ПО ЭТИМ ЧИСЛАМ СУДИТЬ НЕЛЬЗЯ.  Сохранённые прогоны считались с нашим
слоем заплаток: `job.log` тех же каталогов перечисляет «детекция макета в
двенадцать взглядов» и «блоки text, похожие на таблицу, идут на переспрос».
Поэтому сравнивать ЧИСЛО ТАБЛИЦ у пайплайна и у нас бессмысленно: у
пайплайна оно получено переименованием ярлыков нашей же рукой, а не
библиотекой.  Сравнимо только то, что заплатки не трогали, — порядок чтения и
удаление рамок, оба пункта выше.

ЧЕГО ЭТОТ МОДУЛЬ НЕ ДЕЛАЕТ И НЕ ДОЛЖЕН.  Не сливает рамки, не режет их
поперёк межколонника, не переспрашивает, не разрешает конфликт `{table,
text}`.  Отбор по порогу — единственное, что здесь происходит, и порог берётся
из самих весов.  Сырой ответ графа сохраняется ЦЕЛИКОМ, до отбора: иначе
порог, единственное наше вмешательство, нельзя переиграть, не заплатив за
пересчёт.
"""
import hashlib
import os

from ..run import knobs
from .base import Block, Page, Recognizer

# Каталог, куда paddlex складывает официальные веса.  Соглашение чужой
# библиотеки, а не наша настройка: `LAYOUT_MODEL_DIR` пуст ровно затем, чтобы
# сказать «возьми там, где они лежат по умолчанию».  Разрешённый путь уезжает
# в отпечаток — гадать потом не придётся.
PADDLEX_MODELS = os.path.expanduser("~/.paddlex/official_models")


class WeightsMissing(RuntimeError):
    """Весов нет или они неполны.  Обычная ошибка, а не выход из программы.

    Не `SystemExit`: адаптер — библиотека, и стенд обязан уметь поймать это
    как всякую другую беду, а не умереть вместе с процессом.
    """


def weights_dir() -> str:
    """Где лежат веса детекции. Пустая ручка — соглашение paddlex."""
    d = knobs.knob("LAYOUT_MODEL_DIR")
    if d:
        return d
    return os.path.join(PADDLEX_MODELS, knobs.knob("LAYOUT_MODEL_NAME") + "_onnx")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class DocLayout(Recognizer):
    """PP-DocLayoutV2 (ONNX) напрямую: рамки, ярлыки, порядок чтения.

    `read()` возвращает `Page` без единого символа текста: `content` у всех
    блоков `None`, `kind` — `"none"`.  Текст читает вторая половина первого
    уровня, и это отдельный распознаватель.
    """

    name = "doclayout-onnx"

    def __init__(self, model_dir: str | None = None):
        import onnxruntime as ort
        import yaml

        self.dir = model_dir or weights_dir()
        self.onnx = os.path.join(self.dir, "inference.onnx")
        cfg_path = os.path.join(self.dir, "inference.yml")
        missing = [p for p in (self.onnx, cfg_path) if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"нет весов детекции макета в {self.dir}: не хватает "
                f"{', '.join(os.path.basename(m) for m in missing)}.\n"
                f"Задайте каталог ручкой LAYOUT_MODEL_DIR или положите веса по "
                f"умолчанию paddlex ({PADDLEX_MODELS}).")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # Словарь ярлыков берём из ВЕСОВ, а не из yaml пайплайна: у того
        # комментарии к индексам врут (там `9: footer`, `13: header`,
        # `23: text`, а на деле 9 — `footer_image`, 13 — `header_image`,
        # 23 — `vertical_text`).  Индекс 21 = `table` сходится в обоих,
        # поэтому ошибку и не замечали.
        self.labels: list[str] = list(cfg["label_list"])

        # Предобработка — тоже из весов.  Ни одно из этих чисел не наше.
        #
        # `target_size` хранится как (ВЫСОТА, ШИРИНА): так его читает
        # `Resize.generate_scale` в PaddleDetection (`resize_h, resize_w =
        # self.target_size`).  При 800x800 перестановка невидима, поэтому
        # держим порядок явно и называем поля по имени — иначе первые же
        # неквадратные веса дадут перекошенный масштаб, а рамки останутся
        # правдоподобными.
        rz = next(p for p in cfg["Preprocess"] if p.get("type") == "Resize")
        self.target_h, self.target_w = (int(v) for v in rz["target_size"])
        self.keep_ratio = bool(rz.get("keep_ratio", False))
        if self.keep_ratio:
            # `read()` жмёт растр ровно в target_h x target_w. При keep_ratio
            # это неверно: понадобилась бы подложка, и её надо было бы вычесть
            # из координат обратно. Веса с keep_ratio отказываемся считать
            # ГРОМКО — молча они дали бы правдоподобные и смещённые рамки.
            raise WeightsMissing(
                "в весах keep_ratio: true, а адаптер жмёт растр без подложки. "
                "Рамки вышли бы смещёнными и правдоподобными сразу.")
        self.interp = int(rz.get("interp", 2))
        self.native_threshold = float(cfg.get("draw_threshold", 0.5))

        # Нормализация читается из весов, а не подразумевается. У этих весов
        # `norm_type: none`, mean 0, std 1 — то есть только деление на 255.
        # Пока это так, разница невидима; на первых же весах с mean/std
        # молчаливое подразумевание дало бы правдоподобные, но неверные рамки.
        nm = next((p for p in cfg["Preprocess"]
                   if p.get("type") == "NormalizeImage"), None)
        self.norm_type = (nm or {}).get("norm_type", "none")
        self.norm_mean = [float(v) for v in (nm or {}).get("mean", [0.0] * 3)]
        self.norm_std = [float(v) for v in (nm or {}).get("std", [1.0] * 3)]
        self.norm_scale = bool((nm or {}).get("is_scale", True))
        if self.norm_type not in ("none", "mean_std"):
            raise WeightsMissing(
                f"незнакомая нормализация {self.norm_type!r} в inference.yml: "
                f"подставить свою значило бы кормить модель не тем.")
        self.channel_order = "rgb"

        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())

    # ------------------------------------------------------------- пороги
    def thresholds(self) -> dict[str, float]:
        """Порог по КАЖДОМУ из 25 классов, без умолчаний по дороге.

        Так, а не словарём с одним ключом, и это оплачено: в постобработке
        paddlex словарь порогов с одним классом молча ставит остальным 0.5,
        то есть «понизить порог таблиц» меняло поведение всех классов сразу.
        Здесь отбор пишем мы, и правило то же — перечислить все.

        `table` берёт своё значение из `LAYOUT_TABLE_THRESHOLD`, остальные
        двадцать четыре — из `LAYOUT_SCORE_THRESHOLD`.  Две ручки, а не одна,
        потому что таблица — единственный класс, чей порог в этом проекте уже
        подкручивали, и след этого должен быть виден отдельно.
        """
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        table = float(knobs.knob("LAYOUT_TABLE_THRESHOLD"))
        return {lab: (table if lab == "table" else common) for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """Чем ДЕЙСТВУЮЩИЕ пороги отличаются от родного порога весов.

        Сравнивается значение, а не умолчание реестра.  Прежняя редакция
        сверяла `KNOB[...].default` — и `LAYOUT_SCORE_THRESHOLD=0.99` проходил
        молча, то есть сторож спал ровно в том случае, ради которого написан.
        """
        out = []
        for name in ("LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD"):
            v = float(knobs.knob(name))
            if abs(v - self.native_threshold) >= 1e-9:
                out.append(f"{name}={v} против родного "
                           f"draw_threshold={self.native_threshold}")
        return out

    # -------------------------------------------------------------- отпечаток
    def model_name(self) -> str:
        """Имя модели — из ВЕСОВ (`Global.model_name`), а не из ручки.

        `LAYOUT_MODEL_NAME` выбирает лишь каталог по умолчанию (см.
        `weights_dir`); при заданном `LAYOUT_MODEL_DIR` она к лежащим там
        весам отношения не имеет вовсе. Замер: с
        `LAYOUT_MODEL_DIR=~/.paddlex/official_models/PP-DocLayoutV3_onnx` и
        умолчанием ручки слепок писал «модель: PP-DocLayoutV2» рядом с sha256
        весов V3, а в журнал шла строка «PP-DocLayoutV2 из ...V3_onnx».

        Почему это не ловится ничем другим: словари ярлыков у V2 и V3
        совпадают ПОБАЙТОВО (по 25 классов), родной `draw_threshold` у обоих
        0.5 — значит ни сторож политики (`policy.for_labels` выбирает по
        словарю), ни `threshold_drift` подмену V2 на V3 не видят по
        построению. У `PP-DocLayout_plus-L` словарь другой (20 классов), его
        политика зовётся иначе и в журнал попадает — эта подмена видна и без
        имени; невидима именно пара V2/V3.
        """
        import yaml

        cfg_path = os.path.join(self.dir, "inference.yml")
        with open(cfg_path, encoding="utf-8") as f:
            g = yaml.safe_load(f).get("Global") or {}
        # Веса без имени — это «не объявлено», а не повод подставить ручку:
        # молчаливая подстановка и есть та самая беда, что здесь чинится.
        return g.get("model_name") or "не объявлено в весах"

    def knobs_read(self) -> tuple[str, ...]:
        """Ручки, которые читает ЭТОТ адаптер. Сверено grep-ом по файлу.

        `knobs.knob()` зовётся здесь пять раз в четыре имени: `LAYOUT_MODEL_DIR`
        и `LAYOUT_MODEL_NAME` — в `weights_dir()`, `LAYOUT_SCORE_THRESHOLD` и
        `LAYOUT_TABLE_THRESHOLD` — в `thresholds()` и `threshold_drift()`,
        `LAYOUT_MODEL_NAME` ещё раз в `fingerprint()` (поле «имя по ручке»).

        Обе весовые объявлены БЕЗУСЛОВНО, хотя `weights_dir()` зовётся только
        при `DocLayout()` без каталога: ручка, действующая хоть на одном пути,
        действующая. Обратная осторожность стоила бы дороже — «эта ручка вас
        не касается» на прогоне, где она решила, какие веса подняли.
        """
        return ("LAYOUT_MODEL_NAME", "LAYOUT_MODEL_DIR",
                "LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD")

    def label_map(self) -> dict[str, str]:
        """Словарь модели и есть общий: ярлыки никуда не переводятся."""
        return {}

    def fingerprint(self) -> dict:
        """Чем этот прогон отличается от другого. Уезжает в слепок целиком."""
        return {
            "имя": self.name,
            "модель": self.model_name(),
            # Ручка стоит рядом с именем из весов НЕ для красоты: их
            # расхождение и есть подмена весов, и видно её только так.
            "имя по ручке": knobs.knob("LAYOUT_MODEL_NAME"),
            "каталог весов": self.dir,
            "sha256 весов": _sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "исполнители": self.providers,
            "вход": {"высота": self.target_h, "ширина": self.target_w,
                     "keep_ratio": self.keep_ratio, "interp": self.interp,
                     "порядок каналов": self.channel_order,
                     "нормализация": {"тип": self.norm_type,
                                      "делить на 255": self.norm_scale,
                                      "mean": self.norm_mean,
                                      "std": self.norm_std}},
            "родной порог": self.native_threshold,
            "порядок чтения": ("ранг модели" if getattr(self, "has_order", True)
                               else "НАШ, позиция в списке: модель ранга не даёт"),
            "пороги по классам": self.thresholds(),
            "расхождение порога": self.threshold_drift(),
            "словарь ярлыков": self.labels,
            # Свод словарей объявляется, даже когда он пуст: пустой словарь
            # значит «словарь модели и есть общий», и это ЗНАЧЕНИЕ.
            "свод ярлыков": self.label_map(),
            # Промтов у детектора нет вовсе — тоже значение, а не пропуск.
            "промты": {},
        }

    # ------------------------------------------------------------------ счёт
    def read(self, image_path: str, index: int, dpi: float) -> Page:
        """Прочесть страницу-картинку: рамки, ярлыки, порядок. Текста нет."""
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"не читается растр страницы: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        # BGR -> RGB: cv2 читает BGR, PaddleDetection Decode переводит в RGB.
        # ЧЕМ ЭТО НЕ ПРОВЕРЕНО: синтетический стенд ахроматичен — `_age`
        # переводит страницу в серое, — а на сером перестановка каналов
        # невидима. То есть порядок взят из чужого кода и НЕ подтверждён
        # замером. Проверять его надо на цветной странице, и до тех пор это
        # соглашение, а не факт.
        x = rz[:, :, ::-1].astype(np.float32)
        if self.norm_scale:
            x /= 255.0
        if self.norm_type == "mean_std":
            x = (x - np.array(self.norm_mean, np.float32)) / np.array(
                self.norm_std, np.float32)
        x = x.transpose(2, 0, 1)[None]
        # Число выходов графа НЕ фиксировано. У PP-DocLayoutV2 их два — рамки
        # [N,8] и счётчик; у PP-DocLayoutV3 три — рамки [N,7], счётчик и
        # матрица отношений порядка чтения [N,200,200]. Жёсткая распаковка на
        # два роняла прогон на первой же странице новых весов, то есть
        # обновление модели упиралось в одну строку.
        outs = self.sess.run(None, {
            "image": x,
            "im_shape": np.array([[float(self.target_h),
                                   float(self.target_w)]], np.float32),
            "scale_factor": np.array([[self.target_h / h,
                                       self.target_w / w]], np.float32)})
        out = outs[0]
        if out.ndim != 2 or out.shape[1] < 6:
            raise RuntimeError(
                f"первый выход графа {out.shape}: ждали таблицу рамок вида "
                f"[N, >=6] (класс, счёт, четыре координаты). Разбирать её "
                f"наугад значит выдумать рамки.")
        # Шесть колонок значит, что РАНГА ПОРЯДКА ЧТЕНИЯ У МОДЕЛИ НЕТ: у
        # PP-DocLayout_plus-L указательной сети ещё не было, её добавил V2.
        # Это ЗНАЧЕНИЕ, а не пропуск, и в отпечаток оно уходит явно.
        self.has_order = out.shape[1] >= 7

        thr = self.thresholds()
        kept, rejected = [], {}
        for row in out:
            cid, score = int(row[0]), float(row[1])
            if not 0 <= cid < len(self.labels):
                continue
            label = self.labels[cid]
            if score < thr[label]:
                # Лучший ОТВЕРГНУТЫЙ по классу. Без него «table 0» читается
                # как «таблиц на странице нет», а означать может «таблица
                # была, но на 0.03 ниже порога» — разные вещи, и вторая
                # решается ручкой, а не моделью.
                if score > rejected.get(label, 0.0):
                    rejected[label] = score
                continue
            kept.append((row, label, score))

        # Порядок чтения.  Граф отдаёт восемь чисел на рамку: класс, score,
        # четыре координаты и ранг — дважды, причём шестой столбец есть в
        # точности округление седьмого (проверено на 6000 строк, совпадение
        # 6000 из 6000). Сортировка по любому из них даёт один порядок.
        #
        # В `Block.order` кладём РАНГ САМОЙ МОДЕЛИ, а не позицию в нашей
        # сортировке. Разница существенна дважды:
        #
        #  * ранги идут с ДЫРАМИ — на месте рамок, снесённых порогом. Наша
        #    сплошная нумерация стирала след, и два прогона с разными порогами
        #    давали несравнимые `order` для одной и той же рамки;
        #  * ранги бывают СВЯЗАНЫ: на 18 страницах из 65 нашлось 48 рамок с
        #    точно совпадающим рангом, и среди них пары `{table, text}` на
        #    одном прямоугольнике. Устойчивая сортировка разрешала связку
        #    молча — то есть мы решали за модель, кто читается раньше, ровно
        #    там, где обещали не решать. Теперь связка доезжает связкой, и
        #    разрешать её будет объявленная политика уровнем выше.
        # Связку рангов НЕ разрешаем: устойчивая сортировка по одному рангу
        # оставляет связанные рамки в том порядке, в каком их отдал граф.
        # Прежняя редакция добавляла вторым ключом ЯРЛЫК — и связку {table,
        # text} на одном прямоугольнике разрешал алфавит: `table` всегда шёл
        # раньше `text`. Это ровно то решение за модель, которого мы обещали
        # не принимать, и сборщик HTML брал его как порядок чтения.
        if self.has_order:
            kept.sort(key=lambda t: float(t[0][6]))
        # Порядка у модели нет — тогда `order` это НАША позиция в списке, и
        # так и записано в отпечатке. Выдать её за ранг модели значило бы
        # приписать модели порядок, которого она не давала.
        ranks = ([int(round(float(r[6]))) for r, _l, _s in kept]
                 if self.has_order else list(range(len(kept))))
        ties = len(ranks) - len(set(ranks))
        blocks = [
            Block(block_id=i, box=(float(r[2]), float(r[3]),
                                   float(r[4]), float(r[5])),
                  label=label, score=score, order=rank)
            for i, ((r, label, score), rank) in enumerate(zip(kept, ranks))]

        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # Ответ графа ЦЕЛИКОМ, до отбора. Порог — единственное наше
            # вмешательство в этом модуле, и улику под него нельзя выбрасывать:
            # иначе переиграть порог можно только заплатив за пересчёт.
            raw={"строк на выходе": int(out.shape[0]),
                 "колонок": int(out.shape[1]),
                 "выходов графа": len(outs),
                 "все строки": [[float(v) for v in r] for r in out]},
            meta={"распознаватель": self.name, "растр": image_path,
                  "рамок принято": len(kept),
                  "связок рангов": ties,
                  # ЧЕЙ ЭТО ПОРЯДОК — говорим МЕТРИКЕ, а не только слепку.
                  # Отпечаток объявлял это и раньше, но `metrics._has_order`
                  # читает `meta` СТРАНИЦЫ, а не отпечаток, и без поля берёт
                  # умолчание «ранг модели». У шестиколоночной сборки
                  # (PP-DocLayout_plus-L; веса лежат рядом с V2 и включаются
                  # ручкой LAYOUT_MODEL_DIR) ранга нет вовсе, `order` — наша
                  # нумерация строк графа, и на лежащих прогонах plus-L
                  # метрика печатала «согласовано» 29/36/41/44/46/44 % по
                  # шести стендам вместо «НЕ СВЕРЯЕТСЯ». Это ноль от
                  # непонимания, выданный процентом, да ещё и низким: он
                  # читается как «модель читает страницу не в том порядке».
                  #
                  # Что это шум, а не оценка, показала сама батарея: проба
                  # «порядок чтения перевёрнут: упало» на тех же шести
                  # прогонах давала НЕТ, потому что переворот НАШЕЙ нумерации
                  # поднимал согласие до 71/64/59/56/54/56 % — величина
                  # болталась вокруг половины. С этой строкой проба печатает
                  # «нет данных», и непойманных порч на plus-L стало на одну
                  # меньше в каждом из шести прогонов; на девяти стендах V2
                  # (настоящие ранги) как было 0, так и осталось.
                  #
                  # Слово «наш» СО СТРОЧНОЙ — тот самый признак, по которому
                  # сторож узнаёт наш порядок. С заглавной, как в `fingerprint`
                  # выше, он его НЕ видит (проверено: `_has_order` на «НАШ...»
                  # = True). Меняя здесь слова, строчную сохранить.
                  "порядок чтения": ("ранг модели" if self.has_order else
                                     "наш, позиция в списке: "
                                     "модель ранга не даёт"),
                  "лучший отвергнутый по классам": rejected})
