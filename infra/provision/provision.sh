#!/usr/bin/env bash
# Разворачивание окружения на арендованной машине — то, что раньше было
# слоями образа.
#
# Смысл переноса: docker качает три слоя одновременно и по одному потоку на
# слой, а реестр режет соединение до ~25 Мбит/с — итого 76 Мбит/с потолка
# независимо от канала машины.  uv и hf открывают десятки соединений и в тот
# же канал (1500 Мбит/с у типовой машины) укладываются на порядок быстрее.
#
# Каждый шаг печатает своё время: если однажды станет медленно, будет видно
# какой именно шаг, а не «старт долгий».
set -euo pipefail

ENVDIR=${ENVDIR:-/opt/env}
MODELS=${MODELS:-/models}
HERE=$(cd "$(dirname "$0")" && pwd)

export UV_LINK_MODE=copy
export UV_HTTP_TIMEOUT=180
# Xet сам режет файл на чанки и тянет их параллельно; hf_transfer устарел.
export HF_HUB_DISABLE_PROGRESS_BARS=1

step() {
    local label="$1"; shift
    local t0 t1
    t0=$(date +%s)
    "$@"
    t1=$(date +%s)
    printf '== %-22s %4dс\n' "$label" "$((t1 - t0))"
}

step "python" uv python install 3.12
step "окружение" uv venv "$ENVDIR" --python 3.12

export VIRTUAL_ENV="$ENVDIR"
export PATH="$ENVDIR/bin:$PATH"

# --torch-backend=cu130 выбирает колёса CUDA 13 по драйверу машины.  На
# раннере без драйвера он бы дал CPU-сборку, но здесь драйвер есть.
step "колёса" uv pip install -r "$HERE/requirements.in" --torch-backend=cu130

step "веса VL" hf download PaddlePaddle/PaddleOCR-VL \
    --local-dir "$MODELS/vl"
step "веса детектора" hf download PaddlePaddle/PP-DocLayoutV2_onnx \
    --local-dir "$MODELS/layout"

echo "-- размеры --"
du -sh "$ENVDIR" "$MODELS"/* 2>/dev/null || true
echo "-- проверка --"
python -c "import torch, vllm; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
