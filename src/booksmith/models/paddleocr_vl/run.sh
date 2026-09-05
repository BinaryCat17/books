#!/usr/bin/env bash
# Исполняется НА арендованной машине: разворачивает окружение, поднимает vLLM
# и зовёт entrypoint.py, который читает блоки книги.
#
#   bash run.sh input.pdf detect outputs [порт] [страницы] [словарь ярлыков]
#
# ЧТО ЗДЕСЬ ОПЛАЧЕНО КРОВЬЮ и не должно переписываться заново: подъём vLLM
# через setsid и убийство ГРУППЫ процессов. Сироты APIServer и EngineCore
# копились по одной за прогон, каждая держала 60% видеопамяти, а проверка
# здоровья это скрывала — `curl /v1/models` отвечала сирота, и скрипт считал,
# что поднял сервер сам. Отсюда же и проверка имени модели в entrypoint.py:
# «жив ли» и «как тебя зовут» — разные вопросы.
set -uo pipefail

WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"
DETECT="${2:-$WORK/detect}"
OUT="${3:-$WORK/outputs}"
PORT_ARG="${4:-}"
PAGES="${5:--}"
POLICY="${6:-PP-DocLayoutV2}"
MODEL="${MODEL_NAME:-PaddleOCR-VL-1.6-0.9B}"
PORT="${PORT_ARG:-${PORT:-8118}}"
RESUME="${RESUME:-1}"

mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== разворачиваю окружение ==="
bash "$WORK/provision.sh" || { log "разворачивание не удалось"; exit 1; }

export VIRTUAL_ENV=/opt/env
export PATH="/opt/env/bin:$PATH"
# Форма `${X:-…}`, а не безусловное присваивание.  Прежде эти три строки
# затирали то, что оператор задал у себя и что приехало сюда через
# `knobs.passthrough()`: слепок записал бы одно, прогон отработал бы на
# другом.  Ровно этой болезнью и был знаменит `VL_MODEL_DIR` — ручка,
# решающая, какие веса поднимет vLLM, и невидимая в коде задания.
#
# Правые части — ОСОЗНАННЫЙ ДОЛГ, а не забывчивость, и вот его точная
# граница. `spec()` рядом теперь шлёт сюда `knobs.passthrough()`, то есть всё,
# что оператор ЗАДАЛ; умолчания он не подставляет нарочно — у них одно место
# жительства, реестр. Значит эти три строки — умолчания ДЛЯ СЛУЧАЯ, КОГДА
# ОПЕРАТОР МОЛЧАЛ, и они обязаны совпадать с реестром. Расхождение поймает
# `tests/test_knobs.py`, который сверяет правые части `${X:-…}` с ним.
export VL_MODEL_DIR="${VL_MODEL_DIR:-/models/vl}"
# `LAYOUT_MODEL_DIR` и `PADDLE_PDX_MODEL_SOURCE` отсюда УБРАНЫ вместе с качкой
# весов детектора: макет считается ДОМА, на процессоре и бесплатно, а на бокс
# приезжает готовым каталогом `detect/`. Ни один потребитель этих двух
# переменных на боксе не поднимается, и `books read` детектор не зовёт вовсе.
# Веса лежат распакованным каталогом, поэтому vLLM получает путь, а не имя.
# VL_MODEL_DIR к этому месту непуст всегда, ветка `:-` недостижима.
SERVE_MODEL="$VL_MODEL_DIR"

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
# Печаталась версия paddleocr — единственный потребитель полутора гигабайт
# `paddleocr`+`paddlepaddle`+`opencv` в constraints, и тот ради строки в
# журнале. Чтение блоков их не импортирует; вендор вдобавок прямо советует
# держать paddle и vllm в РАЗНЫХ окружениях. Спрашиваем то, что вправду решает
# прогон.
python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__)" 2>/dev/null \
  || log "vllm или torch не импортируются — считать будет нечем"

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
  export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
  # По умолчанию vLLM забирает 90% видеопамяти, и детекции макета не
  # остаётся.  Но и 0.75 мало: ONNX Runtime держит арену в 5.41 ГБ (замерено
  # дважды, с батчем детектора 4 и 64 — цифра одна и та же, арена растёт
  # жадно и от батча почти не зависит), vLLM берёт 18.02 ГБ, вместе это
  # 23.43 из 23.52 ГБ карты, и падает уже сам vLLM:
  #   torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 134.00 MiB
  # С PP-DocLayoutV2 те же 0.75 проходили — арена V3 просто больше.
  # 0.60 оставляет детекции 9 ГБ.  KV-кеш при этом ~11 ГБ на модель в 0.9B —
  # всё ещё несуразно много, узким местом он не станет.
# Порт мог остаться занят движком прошлого прогона.  fuser и ss в образе
  # отсутствуют (Dockerfile ставит только rsync, zstd, curl и библиотеки), так
  # что искать держателя порта нечем — бьём по имени процесса.  Своей оболочки
  # это не касается: в её командной строке нет ни "vllm serve", ни "VLLM::".
  # ИСКАТЬ НЕЧЕМ — ЗНАЧИТ СКАЗАТЬ ОБ ЭТОМ, А НЕ НАПЕЧАТАТЬ «ЧУЖИХ НЕТ».
  # `pgrep` в образе не было, и эта строка выдавала код 127, а `else` печатал
  # «чужих процессов vLLM на машине нет» независимо от факта — говорящий ноль.
  # Теперь `procps` в образе есть (infra/base/Dockerfile), но проверка
  # остаётся: образ пересобирают не каждый день, а сирота держит 60%
  # видеопамяти.
  if ! command -v pgrep >/dev/null 2>&1; then
    log "ИСКАТЬ НЕЧЕМ: в образе нет pgrep — сказать, остались ли чужие "
    log "процессы vLLM, невозможно. Это НЕ «их нет». Пересобери образ "
    log "(infra/base/Dockerfile ставит procps)"
  else
    STALE=$(pgrep -f "vllm serve" 2>/dev/null | tr '\n' ' ')
    if [ -n "$STALE" ]; then
      log "на машине остались процессы vLLM ($STALE) — прибираю"
      pkill -f "vllm serve" 2>/dev/null; pkill -f "VLLM::" 2>/dev/null
      sleep 3
      pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f "VLLM::" 2>/dev/null
      sleep 2
    else
      log "чужих процессов vLLM на машине нет (спрошено pgrep)"
    fi
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

  # Уборка вынесена в ловушку, а не стоит в конце: до конца скрипт доходит не
  # всегда.  Путь `exit 1` при неподнявшемся сервере уборку проходил мимо, а
  # снятие по таймауту не даёт выполнить ни строки — box.run() убивает
  # локальный ssh-клиент, и здесь всё умирает по SIGPIPE на tee.
  #
  # Это стало важнее после setsid: раньше разрыв ssh мог снести сервер по
  # SIGHUP, теперь он от сессии отвязан намеренно, и сирота была бы
  # гарантирована, а не случайна.
  _cleaned=0
  cleanup() {
    [ "$_cleaned" = 1 ] && return; _cleaned=1
    if [ -n "${SRV:-}" ]; then
      # После setsid PID совпадает с идентификатором группы, так что бьём по
      # группе и забираем APIServer с EngineCore вместе с родителем.
      kill -- "-$SRV" 2>/dev/null || kill "$SRV" 2>/dev/null
      sleep 2
      kill -9 -- "-$SRV" 2>/dev/null
    fi
    # Подчистка на случай, если группа не забрала всех: EngineCore не держит
    # сокет порта и переживал и родителя, и освобождение порта.  Своей оболочки
    # это не касается — в её командной строке нет ни "vllm serve", ни "VLLM::".
    pkill -9 -f "vllm serve" 2>/dev/null
    pkill -9 -f "VLLM::" 2>/dev/null
    return 0
  }
  trap cleanup EXIT INT TERM HUP

  for i in $(seq 1 600); do
      # Живость проверяем ДО curl: иначе на первой же итерации ответить может
      # ЧУЖОЙ сервер, и мы решим, что подняли свой.
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
# Пакет booksmith приезжает входным файлом задания и лежит рядом со скриптом:
# дома и здесь исполняется ОДИН И ТОТ ЖЕ код, а не две его редакции.
RESUME_FLAG=""; [ "$RESUME" = "1" ] || RESUME_FLAG="--no-resume"
python "$WORK/entrypoint.py" --pkg "$WORK" --detect "$DETECT" \
       --pdf "$PDF" --out "$OUT" \
       --model "$MODEL" --server "$SERVER_URL" \
       --pages "$PAGES" --policy "$POLICY" $RESUME_FLAG
RC=$?
log "разбор завершён с кодом $RC за $(( $(date +%s) - START ))с"

cleanup

[ "$RC" != 0 ] && { log "=== хвост vllm.log ==="; tail -60 "$OUT/vllm.log" 2>/dev/null; }
log "=== выход ==="; du -sh "$OUT" 2>/dev/null
exit $RC
