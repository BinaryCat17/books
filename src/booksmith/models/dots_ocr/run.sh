#!/usr/bin/env bash
# Runs ON the rented machine. Provisions the environment and starts the run.
#   bash run.sh input.pdf outputs [repeats] [pages|-]
set -uo pipefail
WORK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$WORK/input.pdf}"; OUT="${2:-$WORK/outputs}"
REPEATS="${3:-1}"; PAGES="${4:--}"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== provisioning ==="
if ! bash "$WORK/provision.sh"; then log "provisioning failed"; exit 1; fi

ENVDIR=${ENVDIR:-/opt/env}
export DOTS_DIR=${DOTS_DIR:-${MODELS:-/models}/DotsOCR}
# VRAM fragmentation: the vision encoder allocates large contiguous blocks
# for the attention softmax, and without this flag 3.8 GiB sat reserved and
# unused while it reported OutOfMemory.
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
log "=== run: $PDF -> $OUT, repeats $REPEATS, pages $PAGES ==="
"$ENVDIR/bin/python" "$WORK/entrypoint.py" \
  --pdf "$PDF" --out "$OUT" --repeats "$REPEATS" --pages "$PAGES"
rc=$?
log "=== run finished, code $rc ==="
exit $rc
