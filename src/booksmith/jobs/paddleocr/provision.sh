#!/usr/bin/env bash
# Разворачивание окружения на арендованной машине — то, что раньше было
# слоями образа.
#
# Почему не слоями: docker качает три слоя одновременно и по одному потоку на
# слой, а реестр режет соединение до ~25 Мбит/с — итого 76 Мбит/с потолка
# независимо от канала машины.  Замерено: 6.02 ГБ образа ехали 10.7 минуты.
# uv и hf открывают десятки соединений; те же 11 ГБ ставятся за 82 секунды,
# то есть почти насыщают канал в 1500 Мбит/с.
#
# Скрипт идемпотентен: на прогретой машине (--reuse) всё уже на месте, и он
# отрабатывает за секунды.  Каждый шаг печатает своё время — чтобы «старт
# долгий» всегда разбирался на конкретный шаг.
set -euo pipefail

ENVDIR=${ENVDIR:-/opt/env}
MODELS=${MODELS:-/models}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export UV_LINK_MODE=copy
export UV_HTTP_TIMEOUT=180
export HF_HUB_DISABLE_PROGRESS_BARS=1

step() {
    local label="$1"; shift
    local t0 t1
    t0=$(date +%s)
    "$@"
    t1=$(date +%s)
    printf '== %-18s %4dс\n' "$label" "$((t1 - t0))"
}

step "python" uv python install 3.12
step "окружение" uv venv "$ENVDIR" --python 3.12

export VIRTUAL_ENV="$ENVDIR"
export PATH="$ENVDIR/bin:$PATH"

# Ставится constraints.txt — закреплённое дерево целиком, а не верхний
# уровень: иначе разрешение зависимостей идёт здесь, на арендованной карте,
# и новый релиз любой транзитивной зависимости роняет книгу на середине.
# requirements.in остаётся входом для пересборки этого файла, см. его шапку.
#
# --torch-backend=cu130 нужен и здесь: версия закреплена как 2.13.0+cu130,
# а такой на PyPI нет — она лежит в индексе pytorch.
step "колёса" uv pip install -r "$HERE/constraints.txt" --torch-backend=cu130

step "веса VL" hf download PaddlePaddle/PaddleOCR-VL --local-dir "$MODELS/vl"
# V3, а не V2: именно он стоит в конфигурации пайплайна PaddleOCR-VL-1.6
# по умолчанию.  Набор классов у них совпадает до метки (25 штук, table=21),
# так что это замена без переходников, и V3 вдвое легче: 124 МБ против 204.
step "веса детектора" hf download PaddlePaddle/PP-DocLayoutV3_onnx \
    --local-dir "$MODELS/layout"
