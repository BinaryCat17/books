#!/usr/bin/env bash
# Исполняется НА арендованной машине: разворачивает окружение, поднимает vLLM
# и зовёт entrypoint.py.
#
#   bash run.sh input.pdf outputs
set -uo pipefail

WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"
OUT="${2:-$WORK/outputs}"
# Имя, под которым модель регистрируется в vLLM.  Ровно такое же ставит сам
# olmocr (pipeline.py: --served-model-name olmocr), и менять его незачем.
MODEL="${MODEL_NAME:-olmocr}"
PORT="${PORT:-8118}"
RESUME="${RESUME:-1}"
MODEL_REPO="${OLMOCR_MODEL_REPO:-allenai/olmOCR-2-7B-1025}"

mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== разворачиваю окружение ==="
OLMOCR_MODEL_REPO="$MODEL_REPO" bash "$WORK/provision.sh" \
  || { log "разворачивание не удалось"; exit 1; }

export VIRTUAL_ENV=/opt/env
export PATH="/opt/env/bin:$PATH"
# Веса лежат распакованным каталогом, поэтому vLLM получает путь, а не имя:
# иначе он полез бы в HuggingFace второй раз, уже во время прогона.
MODEL_DIR="/models/$(basename "$MODEL_REPO")"

# flashinfer компилирует ядра на лету и ищет CUDA по CUDA_HOME, иначе по
# /usr/local/cuda — которого у нас нет, CUDA приезжает колёсами.  Без этого
# vLLM не стартует: "Could not find nvcc and default cuda_home ... doesn't
# exist".  Ищем nvcc на месте, а не прописываем путь: раскладка колёс NVIDIA
# уже менялась (сейчас это nvidia/cu13/bin/nvcc).
NVCC=$(find /opt/env -type f -name nvcc -perm -u+x 2>/dev/null | head -1)
if [ -n "$NVCC" ]; then
  export CUDA_HOME="$(dirname "$(dirname "$NVCC")")"
  export PATH="$CUDA_HOME/bin:$PATH"
  log "CUDA_HOME=$CUDA_HOME"
else
  log "nvcc не найден — flashinfer, скорее всего, не соберёт ядра"
fi

log "=== окружение ==="
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap \
           --format=csv,noheader || log "nvidia-smi недоступен"
python -c "import vllm, torch; print('vllm', vllm.__version__, 'torch', torch.__version__)" \
  2>/dev/null || log "vllm не импортируется"
du -sh "$MODEL_DIR" 2>/dev/null | sed 's/^/веса: /'

# ------------------------------------------------------------------ vLLM
# Своего сервера у olmOCR нет: их pipeline.py сам зовёт `vllm serve` и
# ходит в него по OpenAI-совместимому /v1/chat/completions.  Мы поднимаем
# тот же сервер сами — так задача остаётся симметричной paddleocr, а
# управление памятью и порогом остаётся у нас.
if ! python -c "import vllm" 2>/dev/null; then
  log "vllm не установился -> считать нечем, выхожу"
  exit 1
fi

log "=== поднимаю vLLM ($MODEL_REPO) ==="
# flashinfer компилирует сэмплер на месте, и сборка не проходит: колесо
# nvidia-cuda-nvcc приезжает 13.3, torch собран под CUDA 13.0, а заголовки
# cccl внутри flashinfer это ловят — "CUDA compiler and CUDA toolkit headers
# are incompatible".  Чинить совместимость версий незачем: сэмплер нужен
# обычный, а заодно уходит компиляция ядер из времени старта.
export VLLM_USE_FLASHINFER_SAMPLER=0

# Доля видеопамяти.  Здесь она наоборот высокая, а не низкая как у
# paddleocr: там рядом с vLLM жила арена ONNX Runtime на 5.4 ГБ под детекцию
# макета, здесь на карте не работает больше ничего — olmOCR читает страницу
# целиком одной моделью, без детектора.  Но и запас нужен больше: bf16-веса
# это 15.5 ГиБ из 23.5 ГиБ карты, и всё, что останется, поделят KV-кеш и пик
# активаций визуального энкодера.  0.90 оставляет под них около 5.6 ГиБ —
# при 16384 контекста и восьми одновременных страницах этого хватает с
# запасом (страница это ~1.7к входных токенов и до 8к выходных).
GPU_UTIL="${OLMOCR_GPU_UTIL:-0.90}"
MAX_LEN="${OLMOCR_MAX_MODEL_LEN:-16384}"

# --limit-mm-per-prompt '{"video": 0}' ставит и сам olmocr, с объяснением:
# выключенный видеоэнкодер освобождает память под KV-кеш.  Модель — Qwen2.5-VL,
# видео она формально умеет, и без этого флага vLLM резервирует память под
# видеовход, которого у нас не бывает.
#
# Кеш предобработки мультимодалки отключён: каждая страница уникальна, кешу
# в нём нечего ловить, а память он забирает.  Префиксный кеш тоже: общего
# префикса у страниц ровно 90 токенов текста промпта, дальше идёт картинка.
# Порт мог остаться занят движком прошлого прогона.  fuser и ss в образе
# отсутствуют, так что искать держателя порта нечем — бьём по имени процесса.
# Своей оболочки это не касается: в её командной строке нет ни "vllm serve",
# ни "VLLM::".
STALE=$(pgrep -f "vllm serve" 2>/dev/null | tr '\n' ' ')
if [ -n "$STALE" ]; then
  log "на машине остались процессы vLLM ($STALE) — прибираю"
  pkill -f "vllm serve" 2>/dev/null; pkill -f "VLLM::" 2>/dev/null
  sleep 3
  pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f "VLLM::" 2>/dev/null
  sleep 2
else
  log "чужих процессов vLLM на машине нет"
fi

# setsid даёт vLLM собственную группу процессов, иначе группа общая со
# скриптом и убийство группы прибило бы сам скрипт.
setsid nohup vllm serve "$MODEL_DIR" \
      --served-model-name "$MODEL" \
      --host 127.0.0.1 --port "$PORT" \
      --max-model-len "$MAX_LEN" \
      --limit-mm-per-prompt '{"video": 0}' \
      --gpu-memory-utilization "$GPU_UTIL" \
      --no-enable-prefix-caching --mm-processor-cache-gb 0 \
      > "$OUT/vllm.log" 2>&1 &
SRV=$!

# Уборка вынесена в ловушку, а не стоит в конце: до конца скрипт доходит не
# всегда.  Путь `exit 1` при неподнявшемся сервере уборку проходил мимо, а
# снятие по таймауту не даёт выполнить ни строки — box.run() убивает
# локальный ssh-клиент, и здесь всё умирает по SIGPIPE на tee.
#
# Это стало важнее после setsid: раньше разрыв ssh мог снести сервер по
# SIGHUP, теперь он от сессии отвязан намеренно, и сирота была бы
# гарантирована, а не случайна.  У этой задачи цена сироты выше: модель 7B
# при --gpu-memory-utilization 0.90 занимает почти всю карту, а порт 8118
# общий с paddleocr — сирота ломает и её прогоны тоже.
_cleaned=0
cleanup() {
  [ "$_cleaned" = 1 ] && return; _cleaned=1
  if [ -n "${SRV:-}" ]; then
    kill -- "-$SRV" 2>/dev/null || kill "$SRV" 2>/dev/null
    sleep 2
    kill -9 -- "-$SRV" 2>/dev/null
  fi
  pkill -9 -f "vllm serve" 2>/dev/null
  pkill -9 -f "VLLM::" 2>/dev/null
  return 0
}
trap cleanup EXIT INT TERM HUP
SERVER_UP=0
# Ждём дольше, чем у paddleocr: там модель 0.9 ГБ, здесь 15.5 ГиБ весов
# читаются с диска и раскладываются по карте.  600 с — с запасом, но это
# потолок, а не ожидание: обычно укладывается в две-три минуты.
for i in $(seq 1 600); do
    # Живость проверяем ДО curl: иначе ответить может ЧУЖОЙ сервер, и мы
    # решим, что подняли свой.
    if ! kill -0 "$SRV" 2>/dev/null; then
        log "vLLM упал на старте, хвост лога:"; tail -40 "$OUT/vllm.log"; break
    fi
    if curl -sf "http://127.0.0.1:$PORT/v1/models" -o /dev/null 2>/dev/null; then
        SERVER_UP=1; log "vLLM поднялся за ${i}с"
        # В журнал прогонов: по этому числу подгоняется модель выбора
        # машины, потому что прогрев упирается в процессор хоста.
        echo "{\"vllm_startup_s\": $i}" > "$OUT/vllm.json"
        break
    fi
    if ! kill -0 "$SRV" 2>/dev/null; then
        log "vLLM упал на старте, хвост лога:"; tail -40 "$OUT/vllm.log"; break
    fi
    sleep 1
done

# Отката на счёт в процессе нет и быть не может: 7B в transformers считались
# бы на порядок медленнее, и единственным результатом стал бы счёт за час
# аренды.  Лучше сказать честно и сразу.
if [ "$SERVER_UP" = 0 ]; then
  log "vLLM не поднялся — считать нечем, выхожу"
  log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null
  exit 1
fi

# ------------------------------------------------------------------ счёт
log "=== разбираю $(basename "$PDF") ==="
START=$(date +%s)
RESUME_FLAG=""; [ "$RESUME" = "1" ] && RESUME_FLAG="--resume"
python "$WORK/entrypoint.py" --pdf "$PDF" --out "$OUT" \
       --model "$MODEL" --server "http://127.0.0.1:$PORT/v1" \
       --model-repo "$MODEL_REPO" $RESUME_FLAG
RC=$?
log "разбор завершён с кодом $RC за $(( $(date +%s) - START ))с"

cleanup

[ "$RC" != 0 ] && { log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null; }
log "=== выход ==="; du -sh "$OUT" 2>/dev/null
exit $RC
