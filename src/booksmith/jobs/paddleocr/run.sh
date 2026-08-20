#!/usr/bin/env bash
# Исполняется НА арендованной машине: разворачивает окружение, поднимает vLLM
# и зовёт entrypoint.py.
#
#   bash run.sh input.pdf outputs
set -uo pipefail

WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"
OUT="${2:-$WORK/outputs}"
MODEL="${MODEL_NAME:-PaddleOCR-VL-1.6-0.9B}"
PORT="${PORT:-8118}"
RESUME="${RESUME:-1}"

mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== разворачиваю окружение ==="
bash "$WORK/provision.sh" || { log "разворачивание не удалось"; exit 1; }

export VIRTUAL_ENV=/opt/env
export PATH="/opt/env/bin:$PATH"
export VL_MODEL_DIR=/models/vl
export LAYOUT_MODEL_DIR=/models/layout
export PADDLE_PDX_MODEL_SOURCE=huggingface
# Веса лежат распакованным каталогом, поэтому vLLM получает путь, а не имя.
SERVE_MODEL="${VL_MODEL_DIR:-$MODEL}"

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
python -c "import paddleocr; print('paddleocr', paddleocr.__version__)" 2>/dev/null \
  || log "пакет paddleocr не импортируется"

# ------------------------------------------------------------------ vLLM
# Считать VLM в процессе на порядок медленнее, чем через vLLM.  Теперь он
# всегда ставится разворачиванием, но проверка остаётся: она отличает
# «vllm не установился» от «vllm упал на старте», а это разные починки.
SRV=""; SERVER_UP=0
if python -c "import vllm" 2>/dev/null; then
  log "=== поднимаю vLLM ($MODEL) ==="
  log "модель для vLLM: $SERVE_MODEL"
  # --served-model-name обязателен: без него модель регистрируется под своим
  # путём (/models/vl), а клиент спрашивает по имени и получает 404.
  # flashinfer компилирует сэмплер на месте, и сборка не проходит: колесо
  # nvidia-cuda-nvcc приезжает 13.3, torch собран под CUDA 13.0, а заголовки
  # cccl внутри flashinfer это ловят — "CUDA compiler and CUDA toolkit
  # headers are incompatible".  Чинить совместимость версий незачем: сэмплер
  # нужен обычный, а заодно уходит компиляция ядер из времени старта.
  export VLLM_USE_FLASHINFER_SAMPLER=0
  # По умолчанию vLLM забирает 90% видеопамяти, и детекции макета не
  # остаётся.  Но и 0.75 мало: ONNX Runtime держит арену в 5.41 ГБ (замерено
  # дважды, с батчем детектора 4 и 64 — цифра одна и та же, арена растёт
  # жадно и от батча почти не зависит), vLLM берёт 18.02 ГБ, вместе это
  # 23.43 из 23.52 ГБ карты, и падает уже сам vLLM:
  #   torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 134.00 MiB
  # С PP-DocLayoutV2 те же 0.75 проходили — арена V3 просто больше.
  # 0.60 оставляет детекции 9 ГБ.  KV-кеш при этом ~11 ГБ на модель в 0.9B —
  # всё ещё несуразно много, узким местом он не станет.
  # Порт мог остаться занят движком прошлого прогона: vLLM порождает
  # дочерние процессы, и SIGTERM родителю их не забирает.  При --reuse таких
  # сирот накапливается по одной за прогон, каждая держит 60% видеопамяти —
  # на тринадцатом прогоне карта кончилась, запросы повисли, и разбор встал,
  # ничего не написав.  Причём health-check проходил: сирота отвечала на
  # /v1/models, и мы считали, что подняли сервер сами.
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "$PORT/tcp" 2>/dev/null && { log "порт $PORT был занят — прибрал"; sleep 3; }
  else
    OLD=$(ss -lptn "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)
    [ -n "$OLD" ] && { log "порт $PORT держали процессы $OLD — прибираю"; kill -9 $OLD 2>/dev/null; sleep 3; }
  fi

  # setsid даёт vLLM собственную группу процессов.  Без этого группа общая
  # со скриптом, и убийство группы прибило бы сам скрипт — ровно та беда с
  # кодом 144, о которой предупреждает комментарий ниже.
  setsid nohup vllm serve "$SERVE_MODEL" --trust-remote-code \
        --served-model-name "$MODEL" \
        --host 127.0.0.1 --port "$PORT" \
        --max-num-batched-tokens 16384 \
        --gpu-memory-utilization 0.60 \
        --no-enable-prefix-caching --mm-processor-cache-gb 0 \
        > "$OUT/vllm.log" 2>&1 &
  SRV=$!
  for i in $(seq 1 600); do
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
else
  log "vllm не установился -> считать нечем"
fi

# Раньше здесь был откат на счёт VLM в процессе.  Он невозможен: paddle у нас
# CPU-сборки (GPU-сборка тянет 3.69 ГБ и не нужна, детекция ушла на ONNX), а
# doc_vlm требует gpu:0 и падает с "PaddlePaddle is not compiled with CUDA".
# Лучше сказать честно и сразу, чем считать 25 страниц ради этой же ошибки.
if [ "$SERVER_UP" = 0 ]; then
  log "vLLM не поднялся — считать нечем, выхожу"
  log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null
  exit 1
fi

SERVER_URL=""
[ "$SERVER_UP" = 1 ] && SERVER_URL="http://127.0.0.1:$PORT/v1"   # /v1 обязателен

# ------------------------------------------------------------------ счёт
log "=== разбираю $(basename "$PDF") ==="
START=$(date +%s)
RESUME_FLAG=""; [ "$RESUME" = "1" ] && RESUME_FLAG="--resume"
python "$WORK/entrypoint.py" --pdf "$PDF" --out "$OUT" \
       --model "$MODEL" --server "$SERVER_URL" $RESUME_FLAG
RC=$?
log "разбор завершён с кодом $RC за $(( $(date +%s) - START ))с"

# Убиваем всю группу, а не один процесс: vLLM порождает APIServer и
# EngineCore отдельными процессами, и SIGTERM родителю оставляет их жить —
# вместе с занятым портом и видеопамятью.  `pkill -f` здесь нельзя: он
# однажды поймал собственную оболочку этого скрипта и уронил её с кодом 144,
# поэтому бьём по группе именно нашего PID.
if [ -n "$SRV" ]; then
  # После setsid PID процесса совпадает с идентификатором его группы, так
  # что бьём по группе и забираем APIServer с EngineCore вместе с ним.
  kill -- "-$SRV" 2>/dev/null || kill "$SRV" 2>/dev/null
  sleep 3
  kill -9 -- "-$SRV" 2>/dev/null
fi

[ "$RC" != 0 ] && { log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null; }
log "=== выход ==="; du -sh "$OUT" 2>/dev/null
exit $RC
