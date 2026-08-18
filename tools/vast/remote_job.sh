#!/usr/bin/env bash
# Runs INSIDE the vast.ai instance.  Starts the vLLM service, then parses the
# PDF through it.  Weights ship inside the *-offline image, so nothing is
# downloaded here — if you see network activity, you booted the wrong tag.
#
#   bash remote_job.sh /root/ocrjob/input.pdf /root/ocrjob/out
set -uo pipefail

# Work out of wherever this script was uploaded to; these images have no
# /workspace, and hardcoding one bit us once already.
WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PDF="${1:-$WORK/input.pdf}"
OUT="${2:-$WORK/out}"
MODEL="${MODEL_NAME:-PaddleOCR-VL-1.6-0.9B}"
PORT="${PORT:-8118}"
LOG=$WORK/job.log

mkdir -p "$OUT"
exec > >(tee -a "$LOG") 2>&1

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== environment ==="
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap \
           --format=csv,noheader || log "nvidia-smi unavailable"
python -c "import paddleocr,sys; print('paddleocr', paddleocr.__version__)" 2>/dev/null \
  || log "paddleocr python package not importable"

# ---------------------------------------------------------------- vLLM server
# Only worth trying where vllm actually exists.  The pipeline image usually
# lacks it and runs the VLM in-process instead; the server image has vllm but
# no pipeline.  Whichever we booted, one of the two paths works.
SERVER_UP=0
SRV=""
if python -c "import vllm" 2>/dev/null; then
  log "=== starting vLLM service ($MODEL) ==="
  nohup paddleocr genai_server --model_name "$MODEL" \
        --host 127.0.0.1 --port "$PORT" --backend vllm \
        > $WORK/vllm.log 2>&1 &
  SRV=$!
else
  log "vllm not installed in this image -> in-process inference"
fi

for i in $(seq 1 300); do
    [ -z "$SRV" ] && break
    if curl -sf "http://127.0.0.1:$PORT/health" -o /dev/null 2>/dev/null \
    || curl -sf "http://127.0.0.1:$PORT/v1/models" -o /dev/null 2>/dev/null; then
        SERVER_UP=1
        log "vLLM up after ${i}s"
        break
    fi
    if ! kill -0 "$SRV" 2>/dev/null; then
        log "vLLM process exited early; tail of vllm.log:"
        tail -40 $WORK/vllm.log
        break
    fi
    sleep 1
done
[ "$SERVER_UP" = 0 ] && log "falling back to in-process inference (slower)"

# ---------------------------------------------------------------- parse
log "=== parsing $(basename "$PDF") ==="
START=$(date +%s)
SERVER_URL=""
# the server itself prints this URL shape: the /v1 suffix is required
[ "$SERVER_UP" = 1 ] && SERVER_URL="http://127.0.0.1:$PORT/v1"

python $WORK/remote_parse.py \
    --pdf "$PDF" --out "$OUT" --model "$MODEL" --server "$SERVER_URL"
RC=$?
END=$(date +%s)

log "parse exited $RC after $((END-START))s"
[ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null

if [ "$RC" != 0 ]; then
    log "=== last 60 lines of vllm.log ==="
    tail -60 $WORK/vllm.log 2>/dev/null
fi

log "=== output ==="
du -sh "$OUT" 2>/dev/null
find "$OUT" -maxdepth 2 -type f | head -20
exit $RC
