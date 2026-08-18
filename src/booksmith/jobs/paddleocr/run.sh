#!/usr/bin/env bash
# Исполняется НА арендованной машине.  Поднимает vLLM, если он в образе есть,
# и зовёт entrypoint.py.  Веса в *-offline образах вшиты, ничего не качается.
#
#   bash run.sh input.pdf outputs
set -uo pipefail

WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"
OUT="${2:-$WORK/outputs}"
MODEL="${MODEL_NAME:-PaddleOCR-VL-1.6-0.9B}"
# В нашем образе веса лежат распакованными каталогами, в образе Baidu — внутри
# ~/.paddlex под своим именем. Один скрипт должен работать в обоих.
SERVE_MODEL="${VL_MODEL_DIR:-$MODEL}"
PORT="${PORT:-8118}"
RESUME="${RESUME:-1}"

mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== окружение ==="
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap \
           --format=csv,noheader || log "nvidia-smi недоступен"
python -c "import paddleocr; print('paddleocr', paddleocr.__version__)" 2>/dev/null \
  || log "пакет paddleocr не импортируется"

# ------------------------------------------------------------------ vLLM
# Считать VLM в процессе на порядок медленнее, чем через vLLM.  В образе
# пайплайна vllm нет вовсе (проверено по истории слоёв: там только
# paddlepaddle-gpu), поэтому запуск идёт только если он действительно есть.
SRV=""; SERVER_UP=0
if python -c "import vllm" 2>/dev/null; then
  log "=== поднимаю vLLM ($MODEL) ==="
  log "модель для vLLM: $SERVE_MODEL"
  # --served-model-name обязателен: без него модель регистрируется под своим
  # путём (/models/vl), а клиент спрашивает по имени и получает 404.
  nohup vllm serve "$SERVE_MODEL" --trust-remote-code \
        --served-model-name "$MODEL" \
        --host 127.0.0.1 --port "$PORT" \
        --max-num-batched-tokens 16384 \
        --no-enable-prefix-caching --mm-processor-cache-gb 0 \
        > "$OUT/vllm.log" 2>&1 &
  SRV=$!
  for i in $(seq 1 600); do
      if curl -sf "http://127.0.0.1:$PORT/v1/models" -o /dev/null 2>/dev/null; then
          SERVER_UP=1; log "vLLM поднялся за ${i}с"; break
      fi
      if ! kill -0 "$SRV" 2>/dev/null; then
          log "vLLM упал на старте, хвост лога:"; tail -40 "$OUT/vllm.log"; break
      fi
      sleep 1
  done
else
  log "vllm в образе нет -> считаю в процессе (медленно)"
fi
[ "$SERVER_UP" = 0 ] && log "работаю без сервиса vLLM"

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

# Убиваем именно наш процесс: `pkill -f` однажды поймал собственную оболочку
# этого скрипта и уронил его с кодом 144.
[ -n "$SRV" ] && kill "$SRV" 2>/dev/null

[ "$RC" != 0 ] && { log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null; }
log "=== выход ==="; du -sh "$OUT" 2>/dev/null
exit $RC
