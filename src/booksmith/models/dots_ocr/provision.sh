#!/usr/bin/env bash
# Разворачивание окружения под dots.ocr. Образ несёт только доставку, всё
# тяжёлое ставится здесь: замер прежней задачи показал, что через docker
# канал выбирается на пять процентов, а через uv и hf — почти целиком.
#
# Скрипт идемпотентен: на прогретой машине отрабатывает за секунды.
set -euo pipefail
ENVDIR=${ENVDIR:-/opt/env}
MODELS=${MODELS:-/models}
export UV_LINK_MODE=copy UV_HTTP_TIMEOUT=180 HF_HUB_DISABLE_PROGRESS_BARS=1
export HF_HOME=${HF_HOME:-$MODELS/hf}

step() { local l="$1"; shift; local t0=$(date +%s); "$@"; local t1=$(date +%s)
         printf '== %-16s %4dс\n' "$l" "$((t1-t0))"; }

step "python"    uv python install 3.12
step "окружение" uv venv "$ENVDIR" --python 3.12 --allow-existing
export VIRTUAL_ENV="$ENVDIR"
# torch отдельной строкой и с индекса cu124: из общего индекса приезжает
# сборка под другую CUDA, и падает это уже на карте, то есть за деньги.
step "torch"  uv pip install --python "$ENVDIR/bin/python" \
  --index-url https://download.pytorch.org/whl/cu124 torch torchvision
# transformers ПРИЖАТ. Новые версии процессора отдают ключ
# `mm_token_type_ids`, а удалённый код dots.ocr его не принимает, и прогон
# падает ValueError на первой же странице — это стоило трёх аренд. Версия
# взята современной самой модели (октябрь 2025).
step "колёса" uv pip install --python "$ENVDIR/bin/python" \
  "transformers==4.51.3" accelerate qwen-vl-utils pymupdf pillow einops \
  huggingface_hub
# Веса тянем ЗАРАНЕЕ и отдельным шагом: иначе их время растворяется в счёте,
# и «модель считает медленно» не отличить от «веса ехали десять минут».
# Веса кладём в каталог БЕЗ ТОЧКИ В ИМЕНИ. Загрузчик удалённого кода
# transformers делает из пути имя пакета, и точка в «dots.ocr» становится
# разделителем: относительный импорт внутри модели падает
# «No module named transformers_modules.rednote-hilab.dots». Это стоило
# аренды. Карточка модели предупреждает об этом же.
export DOTS_DIR="$MODELS/DotsOCR"
step "веса" "$ENVDIR/bin/python" - <<PY
import os
from huggingface_hub import snapshot_download
p = snapshot_download("rednote-hilab/dots.ocr",
                      local_dir=os.environ["DOTS_DIR"])
print("веса в", p, flush=True)
PY
"$ENVDIR/bin/python" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
