"""Сборщик золотого стенда: два места, где он мог соврать молча.

ПРОВЕРОК У ЭТОГО ФАЙЛА НЕ БЫЛО НИ ОДНОЙ, а на его продукте стоят все головные
числа проекта: 698 объектов из 1232, 646 целых по смыслу, 94.0% чернил, выбор
`PP-DocLayoutV2` основой первого уровня. Ни одна из 152 прежних проверок
`annopage.py` не касалась.

Сговор здесь между `annopage.py` и АРХИВОМ AnnoPage, и записан он был только
прозой. Оба дефекта ниже найдены и померены на живом стенде, оба чинились
после находки, и оба умеют вернуться — потому и закреплены.

    порядок классов на веру      метка в разметке это ИНДЕКС, а имя ему даёт
                                 строка N файла `classes.txt`; проверялось
                                 только МНОЖЕСТВО имён. Перестановка `Table` и
                                 `Vignette` проходила молча, и в замере
                                 становилось 1121 объект вместо 1232, таблиц
                                 13 вместо 124. Рядом, в том же архиве, лежит
                                 второй источник той же карты — `dataset.yaml`,
                                 и он не читался ни разу

    истина стёрта до сторожей    `truth/` чистился до главного цикла, а
                                 сторожа `--truth-only` стояли сотней строк
                                 ниже. Опыт на копии стенда: сборка упала
                                 словами «страниц 600, а истина переписана на
                                 5», и к этому мигу от 600 годных файлов
                                 оставалось ПЯТЬ. 595 уничтожены отказом,
                                 который затевался ради их защиты

Стенд здесь СВОЙ, крошечный и синтетический: `raw/annopage` — 3.5 ГБ, его нет
ни на одной чужой машине, и проверка, молча пропускающая себя без него, была
бы ровно тем нулём от непонимания, о котором предупреждает CLAUDE.md.
"""
import json
import os
import shutil
import tempfile

import support

from booksmith import annopage


def _mini(root, names=None, yaml_names=None, pages=2):
    """Крошечный архив формы AnnoPage: две страницы, по одному объекту."""
    names = list(names if names is not None else annopage._classes.__doc__ or [])
    os.makedirs(os.path.join(root, "labels", "test"), exist_ok=True)
    os.makedirs(os.path.join(root, "images", "test"), exist_ok=True)
    with open(os.path.join(root, "classes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    if yaml_names is not None:
        with open(os.path.join(root, "dataset.yaml"), "w",
                  encoding="utf-8") as f:
            f.write("path: x\nnames:\n")
            for i, n in enumerate(yaml_names):
                f.write(f"  {i}: {n}\n")
    import cv2
    import numpy as np
    for k in range(pages):
        stem = f"p{k:03d}"
        with open(os.path.join(root, "labels", "test", stem + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        img = np.full((200, 150, 3), 255, np.uint8)
        img[80:120, 55:95] = 0
        cv2.imwrite(os.path.join(root, "images", "test", stem + ".jpg"), img)


def _real_names():
    """25 имён в том порядке, в каком их объявляет наш собственный свод."""
    return (list(annopage.DIRECT) + list(annopage.DOUBTFUL)
            + list(annopage.INEXPRESSIBLE))


def test_class_order_is_checked_against_the_second_source():
    """Расхождение `classes.txt` и `dataset.yaml` роняет сборку ВСЛУХ.

    Умеет провалиться: снимите сверку — и перестановка двух строк пройдёт
    молча, а весь стенд соберётся под чужими ярлыками. На живом архиве обе
    карты сегодня СОВПАДАЮТ (25 из 25), то есть сторож ставится не по следам
    аварии.
    """
    names = _real_names()
    swapped = list(names)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=swapped, yaml_names=names)
        try:
            annopage._classes(d)
        except annopage.AnnoPageError as e:
            assert "dataset.yaml" in str(e), f"жалоба не про тот файл: {e}"
            return
        raise AssertionError(
            "перестановка двух классов принята молча — метка в разметке это "
            "ИНДЕКС, и вся истина стенда собралась бы под чужими ярлыками")


def test_matching_sources_are_accepted():
    """Обратная сторона: совпадающие карты сборку НЕ роняют.

    Без неё сторож можно было бы «починить», просто запретив всё.
    """
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=names, yaml_names=names)
        assert annopage._classes(d) == names


def test_a_failed_build_does_not_destroy_good_truth():
    """Отказ сторожа НЕ уничтожает истину, которая уже лежала.

    Тот самый дефект: сборка падала правдивыми словами, уже стерев 595 файлов
    из 600. Проверка кладёт заведомо чужую истину, роняет сборку сторожем
    `--truth-only` (pdf, которого нет) и требует, чтобы чужое осталось
    нетронутым — потому что решать, что делать с несовпадением, должен
    человек, а не обломок сборки.
    """
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "raw")
        out = os.path.join(d, "out")
        _mini(root, names=names, yaml_names=names)
        tdir = os.path.join(out, "truth")
        os.makedirs(tdir)
        for k in range(7):
            with open(os.path.join(tdir, f"{k:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"marker": "прежняя истина"}, f)
        before = sorted(os.listdir(tdir))
        try:
            annopage.build(root, out, split="test", truth_only=True,
                           log=lambda *a: None)
        except annopage.AnnoPageError:
            pass
        else:
            raise AssertionError(
                "сборка с --truth-only и без pdf прошла — сторожа нет вовсе")
        after = sorted(os.listdir(tdir))
        assert after == before, (
            f"неудачная сборка тронула истину: было {len(before)} файлов, "
            f"стало {len(after)}. Сторож, уничтожающий то, что защищает, — "
            f"хуже отсутствующего: он ещё и объявляет себя сработавшим")


def test_the_sheet_follows_the_declared_knob():
    """Размер листа считается ИЗ `PAGE_DPI`, а не из зашитого 0.5.

    Смысл размера один: рендер при `PAGE_DPI` обязан отдать ровно исходный
    растр. Зашитое 0.5 верно ровно при умолчании 144; при 288 стенд собрался
    бы про растр вдвое мельче объявленного, а истина продолжала бы писать
    «dpi: 144.0». Ловила это сверка размеров в `metrics` — чужой файл, — а сам
    сборщик молчал.

    Умеет провалиться: верните `w * 0.5`, и лист при 288 останется прежним.
    """
    import pymupdf

    from booksmith.run import knobs

    names = _real_names()
    seen = {}
    for dpi in ("144", "288"):
        with tempfile.TemporaryDirectory() as d:
            root, out = os.path.join(d, "raw"), os.path.join(d, "out")
            _mini(root, names=names, yaml_names=names)
            old = os.environ.get("PAGE_DPI")
            os.environ["PAGE_DPI"] = dpi
            try:
                knobs.knob.cache_clear() if hasattr(knobs.knob, "cache_clear") \
                    else None
                man = annopage.build(root, out, split="test",
                                     log=lambda *a: None)
            finally:
                if old is None:
                    os.environ.pop("PAGE_DPI", None)
                else:
                    os.environ["PAGE_DPI"] = old
            assert man["PAGE_DPI"] == float(dpi), (
                f"манифест не записал ручку: {man['PAGE_DPI']} при {dpi}")
            doc = pymupdf.open(os.path.join(out, "annopage.pdf"))
            seen[dpi] = doc[0].rect.width
            doc.close()
    assert abs(seen["144"] - 2 * seen["288"]) < 0.01, (
        f"лист не поехал за ручкой: при 144 ширина {seen['144']} пт, при 288 "
        f"{seen['288']} пт, а должна быть вдвое меньше. Значит масштаб зашит, "
        f"и стенд, собранный при другом PAGE_DPI, врёт про свой растр молча")
