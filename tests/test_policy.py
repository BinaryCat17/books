"""Полнота политики: ярлык, которого нет в словаре, обязан ронять прогон.

«ПОЛИТИКА ПОЛНА ПО ПОСТРОЕНИЮ, И ЭТО ГЛАВНОЕ В ФАЙЛЕ» — так сказано в
`policy.py`, и цена сказанного известна: в постобработке paddlex словарь
порогов с одним классом молча ставил остальным 0.5. Двадцать шестой класс
новых весов при умолчании молча вылился бы в прозу — «артефактов 40» стало бы
«артефактов 39», и никто бы не заметил.

Проверяется обе стороны сговора: политика знает словарь модели ЦЕЛИКОМ, и
словарь модели знает политику. Пять словарей у пяти детекторов, и путать их
нельзя: `check` сверяет с ОДНИМ названным, а не с объединением.
"""
from booksmith import policy
from booksmith.models import docling_heron, yolox_layout


def test_check_passes_on_its_own_dictionary():
    for name, table in policy.POLICIES.items():
        policy.check(list(table), name)      # молчит — значит сошлось


def test_unknown_label_raises():
    """Лишний ярлык модели — падение с именем ярлыка, а не тихое умолчание."""
    for name, table in policy.POLICIES.items():
        try:
            policy.check(list(table) + ["Chart_2027"], name)
        except policy.UnknownLabel as e:
            assert "Chart_2027" in str(e), f"в жалобе нет ярлыка: {e}"
        else:
            raise AssertionError(
                f"политика {name} проглотила незнакомый ярлык: он молча "
                f"уехал бы в прозу, а число артефактов уменьшилось бы без "
                f"единого слова")


def test_label_missing_from_model_also_raises():
    """И наоборот: `figure` вместо `image` дало бы «артефактов 0» навсегда."""
    for name, table in policy.POLICIES.items():
        labels = sorted(table)[1:]
        try:
            policy.check(labels, name)
        except policy.UnknownLabel as e:
            assert sorted(table)[0] in str(e)
        else:
            raise AssertionError(
                f"политика {name} описывает ярлык, которого у модели нет, и "
                f"молчит: опечатка тут не видна ничем, кроме вечного нуля")


def test_unknown_policy_name_raises():
    try:
        policy.check(["text"], "PP-DocLayoutV9")
    except policy.UnknownLabel as e:
        assert "PP-DocLayoutV9" in str(e)
    else:
        raise AssertionError("политика с выдуманным именем принята")


def test_check_does_not_use_the_union():
    """Сверка идёт с названным словарём, а не с объединением всех пяти.

    Объединение покрывает и чужие ярлыки, и проверка перестала бы ловить как
    раз то, ради чего написана: `Table` из DocLayNet в прогоне V2 — это
    перепутанные веса, а не законный ярлык.
    """
    try:
        policy.check(list(policy.PP_DOCLAYOUT_V2) + ["Table"], "PP-DocLayoutV2")
    except policy.UnknownLabel:
        pass
    else:
        raise AssertionError(
            "чужой ярлык из другого словаря прошёл проверку: значит сверка "
            "идёт с объединением, и перепутанные веса пройдут молча")


def test_role_raises_on_unknown():
    try:
        policy.role("выдуманный_ярлык")
    except policy.UnknownLabel:
        pass
    else:
        raise AssertionError("`role` вернул разряд ярлыку, которого не знает")


def test_every_label_has_one_of_three_roles():
    assert policy.ROLES == ("text", "artifact", "furniture")
    for name, table in policy.POLICIES.items():
        for lab, r in table.items():
            assert r in policy.ROLES, f"{name}/{lab}: разряд {r!r} не из трёх"


def test_union_agrees_with_every_dictionary():
    """`ROLE` — объединение с проверкой на противоречие, и она жива.

    Один ярлык не может значить в двух словарях разное: `formula` артефакт и
    там, и там, а разряд блока не может зависеть от порядка импорта.
    """
    for name, table in policy.POLICIES.items():
        for lab, r in table.items():
            assert policy.ROLE[lab] == r, (
                f"{name}/{lab}: в объединении {policy.ROLE[lab]!r}, в словаре "
                f"{r!r}")
    assert set(policy.ROLE) == set().union(*(set(t) for t in
                                             policy.POLICIES.values()))


def test_for_labels_picks_by_dictionary_not_by_name():
    """Политика выбирается СЛОВАРЁМ модели: имя весов можно перепутать."""
    for name, table in policy.POLICIES.items():
        assert policy.for_labels(list(table)) == name
    for bad in (["text", "table"], [], list(policy.ROLE)):
        try:
            policy.for_labels(bad)
        except policy.UnknownLabel:
            pass
        else:
            raise AssertionError(
                f"под словарь из {len(bad)} ярлыков нашлась политика: "
                f"подходить он не может ни одной")


def test_adapters_and_policies_agree():
    """Сговор через файл: словарь адаптера -> имя его политики.

    `detect.py` зовёт `policy.check` по словарю модели, и разойдись здесь
    что-нибудь — прогон адаптера падал бы на своём же стенде.
    """
    pairs = ((docling_heron.DoclingHeron, list(docling_heron.DEFAULT_LABELS)),
             (docling_heron.DoclingEgret,
              list(docling_heron.EGRET_TO_DOCLING)),
             (yolox_layout.YoloXLayout, list(yolox_layout.LABELS)))
    for cls, labels in pairs:
        assert cls.policy_name in policy.POLICIES, (
            f"{cls.__name__}.policy_name = {cls.policy_name!r}, а такой "
            f"политики нет")
        assert policy.for_labels(labels) == cls.policy_name, (
            f"{cls.__name__}: словарь ярлыков указывает на политику "
            f"{policy.for_labels(labels)!r}, а объявлено {cls.policy_name!r}")
        policy.check(labels, cls.policy_name)


def test_artefacts_are_not_empty_and_are_artefacts():
    """Пустой список артефактов молча превратил бы книгу в сплошной текст."""
    arte = policy.artefacts()
    assert arte, "артефактов нет ни одного: второму уровню нечего резать"
    for lab in arte:
        assert policy.ROLE[lab] == "artifact"
    assert "table" in arte and "Table" in arte


def test_snapshot_carries_whole_dictionary():
    """Слепок несёт политику целиком: без неё число артефактов не истолковать."""
    for name, table in policy.POLICIES.items():
        s = policy.snapshot(name)
        assert s["vocabulary"] == name
        assert s["by_label"] == dict(sorted(table.items())), (
            f"слепок политики {name} неполон: в нём {len(s['by_label'])} "
            f"ярлыков из {len(table)}")
    whole = policy.snapshot()
    assert sorted(whole["vocabularies"]) == sorted(policy.POLICIES)
    assert len(whole["by_label"]) == len(policy.ROLE)
