#!/usr/bin/env bash
# Исполняется НА арендованной машине. Разворачивает окружение и зовёт счёт.
#   bash run.sh input.pdf outputs [повторов] [страницы|-]
set -uo pipefail
WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"; OUT="${2:-$WORK/outputs}"
REPEATS="${3:-1}"; PAGES="${4:--}"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== разворачиваю окружение ==="
if ! bash "$WORK/provision.sh"; then log "разворачивание не удалось"; exit 1; fi

ENVDIR=${ENVDIR:-/opt/env}
export DOTS_DIR=${DOTS_DIR:-${MODELS:-/models}/DotsOCR}
# Фрагментация видеопамяти: кодировщик зрения выделяет большие непрерывные
# куски под софтмакс внимания, и без этого флага 3.8 ГиБ висели
# зарезервированными и неиспользуемыми при OutOfMemory.
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
log "=== счёт: $PDF -> $OUT, повторов $REPEATS, страницы $PAGES ==="
"$ENVDIR/bin/python" "$WORK/entrypoint.py" \
  --pdf "$PDF" --out "$OUT" --repeats "$REPEATS" --pages "$PAGES"
rc=$?
log "=== счёт кончился, код $rc ==="
exit $rc
