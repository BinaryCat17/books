"""YOLOX-layout (unstructured.io): ЕДИНСТВЕННАЯ на стенде не-DETR модель.

Зачем именно она. Четыре других детектора стенда — RT-DETR-L, RT-DETR-L с
масками, RT-DETRv2 и D-FINE — все из одного семейства: фиксированный набор
запросов, однозначное сопоставление венгерским алгоритмом, подавление дублей
как ВЫУЧЕННЫЙ навык. Если слияние соседних блоков идёт от этого устройства,
то модель другой парадигмы обязана вести себя иначе.

YOLOX — свёрточный детектор без якорей, с плотным предсказанием по сетке и
подавлением дублей алгоритмом (NMS), а не обучением. Совсем другой ответ на
тот же вопрос «сколько тут объектов».

ЧТО МЫ ЗДЕСЬ ДЕЛАЕМ С ВЫВОДОМ И ПОЧЕМУ ЭТО НЕ ЗАПЛАТКА. Граф отдаёт СЫРУЮ
сетку: смещения в клетках и логарифм размера. Раскладка по сетке и NMS —
часть инференса самой YOLOX, описанная её авторами, а не наша правка рамок:
без них у модели нет ответа вовсе. Мы ничего не сливаем, не режем и не
двигаем; порог NMS взят родной (0.45), и он объявлен в отпечатке.

ВХОД С ПОДЛОЖКОЙ. 1024x768 с сохранением пропорций и серой подложкой 114 —
так эту модель кормит unstructured. Из пяти детекторов стенда только она не
рвёт пропорции листа, и это само по себе предмет замера: искажение входа уже
показало себя на одном случае из четырёх.
"""
import hashlib
import json
import os

from .base import Block, Page, Recognizer
from ..run import knobs

MODELS = os.path.expanduser("~/.paddlex/official_models")
# Порядок классов — DocLayNet по алфавиту, как их нумерует unstructured.
# Проверено на полосе каталога: класс 5 встал на колонтитул, класс 8 на
# таблицу — то есть `Page-header` и `Table` на своих местах.
LABELS = ("Caption", "Footnote", "Formula", "List-item", "Page-footer",
          "Page-header", "Picture", "Section-header", "Table", "Text", "Title")
STRIDES = (8, 16, 32)
PAD = 114               # серая подложка, как у unstructured
NMS_IOU = 0.45          # родной порог YOLOX
# Подавление дублей ПО КЛАССАМ — так устроен `multiclass_nms` самой YOLOX
# (класс-агностичный режим у неё есть, но выключен по умолчанию). Обёртка
# unstructured могла выбрать иначе; проверить это по их коду мы не смогли,
# поэтому выбор объявлен здесь и уезжает в отпечаток, а не подразумевается.
# Разница видна на рамках разных классов, лежащих на одном месте: при
# подавлении по классам они остаются обе.
NMS_BY_CLASS = True


class WeightsMissing(RuntimeError):
    pass


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class YoloXLayout(Recognizer):
    name = "yolox-layout"
    policy_name = "DocLayNet"

    def __init__(self, model_dir: str | None = None, weights: str | None = None):
        import onnxruntime as ort

        self.dir = model_dir or os.path.join(MODELS, "yolox_layout")
        self.weights = weights or knobs.knob("YOLOX_WEIGHTS") or "yolox_l0.05.onnx"
        self.onnx = os.path.join(self.dir, self.weights)
        if not os.path.exists(self.onnx):
            raise WeightsMissing(
                f"нет {self.onnx}. Скачать из "
                f"huggingface.co/unstructuredio/yolo_x_layout")
        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        shape = self.sess.get_inputs()[0].shape
        # Вход у этой сборки ЖЁСТКИЙ: (1,3,1024,768). Динамики нет, и подать
        # другой размер нельзя — падаем вслух, а не подгоняем молча.
        self.in_h, self.in_w = int(shape[2]), int(shape[3])
        self.labels = list(LABELS)
        out = self.sess.get_outputs()[0].shape
        want = sum((self.in_h // s) * (self.in_w // s) for s in STRIDES)
        if int(out[1]) != want:
            raise WeightsMissing(
                f"выход {out}: клеток {out[1]}, а сетка {STRIDES} на входе "
                f"{self.in_h}x{self.in_w} даёт {want}. Раскладывать наугад "
                f"значит выдумать рамки.")
        if int(out[2]) != 5 + len(self.labels):
            raise WeightsMissing(
                f"выход {out}: колонок {out[2]}, а ждали "
                f"{5 + len(self.labels)} = 4 координаты + объектность + "
                f"{len(self.labels)} классов.")

    def thresholds(self) -> dict[str, float]:
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        return [f"родного порога у сборки нет; действует "
                f"LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"на все {len(self.labels)} классов"]

    def knobs_read(self) -> tuple[str, ...]:
        """Две ручки, сверено grep-ом: `knob()` зовётся здесь трижды.

        `YOLOX_WEIGHTS` — в `__init__` (какие веса брать), `LAYOUT_SCORE_THRESHOLD`
        — в `thresholds()` и `threshold_drift()`. `LAYOUT_TABLE_THRESHOLD` не
        читается: класс `Table` словаря DocLayNet берёт общий порог, отдельного
        у него нет. Имя и каталог paddle-весов к этой модели не относятся
        вовсе — путь собирается из `MODELS` и `self.weights`.

        `YOLOX_WEIGHTS` объявлена, хотя `YoloXLayout(weights=…)` её и не
        прочтёт: `books detect` строит адаптер без аргументов, то есть ручка
        решает веса на всяком прогоне, который вообще попадает в слепок.
        """
        return ("YOLOX_WEIGHTS", "LAYOUT_SCORE_THRESHOLD")

    def label_map(self) -> dict[str, str]:
        return {}

    def fingerprint(self) -> dict:
        return {
            "имя": self.name,
            "модель": f"YOLOX-layout ({self.weights}), unstructured.io",
            "каталог весов": self.dir,
            "sha256 весов": _sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "исполнители": self.providers,
            "вход": {"высота": self.in_h, "ширина": self.in_w,
                     "подложка": PAD, "пропорции сохраняются": True},
            "родной порог": None,
            "пороги по классам": self.thresholds(),
            "расхождение порога": [],
            "словарь ярлыков": self.labels,
            "свод ярлыков": self.label_map(),
            "промты": {},
            "порядок чтения": None,
            # NMS — часть инференса YOLOX, а не наша правка. Объявляем числом.
            "подавление дублей": {"способ": "NMS", "iou": NMS_IOU,
                                  "по классам": NMS_BY_CLASS,
                                  "сверено с обёрткой unstructured": False},
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"не читается растр страницы: {image_path}")
        h, w = img.shape[:2]
        r = min(self.in_h / h, self.in_w / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        canvas = np.full((self.in_h, self.in_w, 3), PAD, np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=1)
        x = np.ascontiguousarray(
            canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32))
        out = self.sess.run(None, {"images": x})[0][0]

        # Раскладка по сетке: смещение в клетках и логарифм размера — так
        # определена сама YOLOX.
        grids, strides = [], []
        for s in STRIDES:
            gh, gw = self.in_h // s, self.in_w // s
            yv, xv = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((gh * gw, 1), s, np.float32))
        g = np.concatenate(grids).astype(np.float32)
        st = np.concatenate(strides)
        cxy = (out[:, :2] + g) * st
        wh = np.exp(out[:, 2:4]) * st
        boxes = np.concatenate([cxy - wh / 2, cxy + wh / 2], 1) / r

        sc = out[:, 4:5] * out[:, 5:]
        cls = sc.argmax(1)
        best = sc.max(1)

        thr = self.thresholds()
        # Порог сохранения сырых строк. Сетку целиком (16128 клеток) в json
        # не кладём, но улика ОБЯЗАНА покрывать всё принятое: порог отбора
        # приезжает из ручки и бывает ниже 0.01, и тогда развёртка порога по
        # слепку врёт вниз — на atlas при LAYOUT_SCORE_THRESHOLD=0.005 из 75
        # принятых рамок 20 не имели в сыром выводе ни одной строки.
        raw_keep = min(0.01, min(thr.values()))
        keep_idx, rejected = [], {}
        for i in range(len(best)):
            lab = self.labels[int(cls[i])]
            if float(best[i]) < thr[lab]:
                if float(best[i]) > rejected.get(lab, 0.0):
                    rejected[lab] = float(best[i])
                continue
            keep_idx.append(i)
        keep_idx = _nms(boxes[keep_idx], best[keep_idx], cls[keep_idx],
                        keep_idx, NMS_IOU, by_class=NMS_BY_CLASS)

        kept = [(self.labels[int(cls[i])], float(best[i]),
                 [float(v) for v in boxes[i]]) for i in keep_idx]
        # Сортировка БЕЗ КОРЗИНЫ. Прежде стояло `round(y/20)`, и двадцать —
        # это пиксели растра: при другом PAGE_DPI соседи по строке
        # переставлялись, а ручки, которая бы это объявила, не было. Теперь
        # порядок задан просто и без магического числа — сверху вниз, при
        # равном верхе слева направо. Он всё равно НАШ, а не модели: метрика
        # это знает по `meta` и порядок по этой модели не сверяет.
        kept.sort(key=lambda t: (t[2][1], t[2][0]))
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # «строк на выходе» — что ВЕРНУЛ граф; «клеток сетки» — сколько
            # их даёт раскладка по STRIDES. Раньше оба брались из
            # out.shape[0], и журнал сверял число с самим собой. Разбивка по
            # уровням — величина, которой из формы выхода не вывести.
            raw={"строк на выходе": int(out.shape[0]),
                 "колонок на выходе": int(out.shape[1]),
                 "клеток сетки": int(len(g)),
                 "клеток по уровням": {
                     str(s): int((self.in_h // s) * (self.in_w // s))
                     for s in STRIDES},
                 "все строки": [[float(cls[i]), float(best[i]),
                                 *[float(v) for v in boxes[i]]]
                                for i in np.where(best >= raw_keep)[0]],
                 "порог сохранения сырых строк": raw_keep},
            meta={"распознаватель": self.name, "растр": image_path,
                  "рамок принято": len(kept), "связок рангов": 0,
                  "порядок чтения": "наш, сверху вниз и слева направо",
                  "подавление дублей": f"NMS iou={NMS_IOU}",
                  "лучший отвергнутый по классам": rejected})


def _nms(boxes, scores, cls, idx, iou_thr, by_class=True):
    """Подавление дублей. `by_class` — как в `multiclass_nms` самой YOLOX."""
    import numpy as np

    keep = []
    groups = np.unique(cls) if by_class else [None]
    for c in groups:
        m = np.where(cls == c)[0] if c is not None else np.arange(len(cls))
        b, s = boxes[m], scores[m]
        order = s.argsort()[::-1]
        while len(order):
            i = order[0]
            keep.append(idx[m[i]])
            if len(order) == 1:
                break
            xx0 = np.maximum(b[i, 0], b[order[1:], 0])
            yy0 = np.maximum(b[i, 1], b[order[1:], 1])
            xx1 = np.minimum(b[i, 2], b[order[1:], 2])
            yy1 = np.minimum(b[i, 3], b[order[1:], 3])
            inter = np.maximum(0, xx1 - xx0) * np.maximum(0, yy1 - yy0)
            a1 = (b[i, 2] - b[i, 0]) * (b[i, 3] - b[i, 1])
            a2 = ((b[order[1:], 2] - b[order[1:], 0])
                  * (b[order[1:], 3] - b[order[1:], 1]))
            iou = inter / np.maximum(1e-9, a1 + a2 - inter)
            order = order[1:][iou <= iou_thr]
    return sorted(keep)
