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

# --torch-backend=cu130 выбирает колёса CUDA 13 по драйверу машины.
step "колёса" uv pip install -r "$HERE/requirements.in" --torch-backend=cu130

step "веса VL" hf download PaddlePaddle/PaddleOCR-VL --local-dir "$MODELS/vl"
step "веса детектора" hf download PaddlePaddle/PP-DocLayoutV2_onnx \
    --local-dir "$MODELS/layout"
