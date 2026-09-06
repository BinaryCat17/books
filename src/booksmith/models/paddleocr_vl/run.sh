#!/usr/bin/env bash
# Runs ON the rented machine: provisions the environment, raises vLLM and
# calls entrypoint.py, which reads the blocks of the book.
#
#   bash run.sh input.pdf detect outputs [port] [pages] [label dictionary]
#
# PAID FOR IN BLOOD here, not to be written anew: raising vLLM through setsid
# and killing the process GROUP. Orphaned APIServer and EngineCore piled up
# one per run, each holding 60% of the video memory, and the health check hid
# it -- `curl /v1/models` was answered by an orphan, and the script decided it
# had raised the server itself. Hence also the model-name check in
# entrypoint.py: "are you alive" and "what is your name" are two questions.
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

log "=== provisioning the environment ==="
bash "$WORK/provision.sh" || { log "provisioning failed"; exit 1; }

export VIRTUAL_ENV=/opt/env
export PATH="/opt/env/bin:$PATH"
# The form `${X:-…}`, not an unconditional assignment.  These lines used to
# overwrite what the operator set at home and what came here through
# `knobs.passthrough()`: the snapshot would record one thing, the run work by
# another.  `VL_MODEL_DIR` was famous for exactly this disease -- the knob
# deciding which weights vLLM raises, invisible in the job code.
#
# The right-hand sides are a DELIBERATE DEBT, not forgetfulness, and here is
# its exact boundary. `spec()` beside this now sends `knobs.passthrough()`,
# that is everything the operator SET; defaults it deliberately leaves alone --
# those have one home, the registry. So this line is the default FOR THE CASE
# WHERE THE OPERATOR WAS SILENT, and it must agree with the registry.
#
# BUT THIS NEIGHBOURING LINE'S VALUE IS NOT COMPARED, and that must be known.
# `VL_MODEL_DIR` has an EMPTY default in the registry -- the owner of the value
# is declared to be the shell -- and there is nothing to compare it with: the
# guard demands only that the registry entry admit as much. Swapping
# `/models/vl` for anything passes silently, proved by mutation. Compared are
# those whose registry default is non-empty: `MODEL_NAME`, `PORT`, `RESUME`,
# `VLLM_USE_FLASHINFER_SAMPLER`. Here stood "these three lines" -- there is ONE
# line under this comment.
#
# A divergence is caught by
# `tests/test_knobs.py::test_shell_defaults_agree_with_the_registry`, which
# compares the right-hand sides of `${NAME:-…}` with the registry -- COUNTING
# BRACES, otherwise the nested `${PORT_ARG:-${PORT:-8118}}` is eaten whole and
# the inner default is not checked at all.
#
# THIS PROMISE LIVED HERE BEFORE THE CHECK DID. There was no comparison at all:
# not one file in `tests/` opened a `.sh`, and `knobs.readers()` looks in the
# shell only for the PRESENCE of `$NAME`, not the value. A promised and absent
# guard is worse than an absent one: it is cited when decisions are made.
export VL_MODEL_DIR="${VL_MODEL_DIR:-/models/vl}"
# `LAYOUT_MODEL_DIR` and `PADDLE_PDX_MODEL_SOURCE` are GONE from here with the
# pulling of the detector weights: layout is computed AT HOME, on the CPU and
# free, and reaches the box as a finished `detect/` directory. Not one consumer
# of those two variables comes up on the box, and `books read` never calls the
# detector at all.
# The weights lie as an unpacked directory, so vLLM is given a path, not a
# name. By here VL_MODEL_DIR is always non-empty -- the export above saw to it.
SERVE_MODEL="$VL_MODEL_DIR"

# flashinfer compiles kernels on the fly and looks for CUDA at CUDA_HOME,
# failing that at /usr/local/cuda -- which we do not have, CUDA arrives as
# wheels.  Without this vLLM does not start: "Could not find nvcc and default
# cuda_home ... doesn't exist".  We search for nvcc in place instead of writing
# the path down: the layout of the NVIDIA wheels has changed once already (it
# is nvidia/cu13/bin/nvcc now).
NVCC=$(find /opt/env -type f -name nvcc -perm -u+x 2>/dev/null | head -1)
if [ -n "$NVCC" ]; then
  export CUDA_HOME="$(dirname "$(dirname "$NVCC")")"
  export PATH="$CUDA_HOME/bin:$PATH"
  log "CUDA_HOME=$CUDA_HOME"
else
  log "nvcc not found -- flashinfer will most likely not build its kernels"
fi

log "=== environment ==="
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap \
           --format=csv,noheader || log "nvidia-smi unavailable"
# The paddleocr version used to be printed -- the sole consumer of the one and
# a half gigabytes of `paddleocr`+`paddlepaddle`+`opencv` in constraints, and
# that for a line in the log. Reading blocks imports none of them; the vendor
# moreover advises outright to keep paddle and vllm in DIFFERENT environments.
# We ask what really decides the run.
python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__)" 2>/dev/null \
  || log "vllm or torch will not import -- there is nothing to compute with"

# ------------------------------------------------------------------ vLLM
# Counting the VLM in-process is an order of magnitude slower than through
# vLLM.  It is now always installed by provisioning, but the check stays: it
# tells "vllm did not install" from "vllm fell over at start", and those are
# different repairs.
SRV=""; SERVER_UP=0
if python -c "import vllm" 2>/dev/null; then
  log "=== raising vLLM ($MODEL) ==="
  log "model for vLLM: $SERVE_MODEL"
  # --served-model-name is mandatory: without it the model registers under its
  # own path (/models/vl), while the client asks by name and gets a 404.
  # flashinfer compiles the sampler in place, and the build does not pass: the
  # nvidia-cuda-nvcc wheel arrives as 13.3, torch is built for CUDA 13.0, and
  # the cccl headers inside flashinfer catch that -- "CUDA compiler and CUDA
  # toolkit headers are incompatible".  Repairing version compatibility is
  # pointless: the sampler wanted is the ordinary one, and kernel compilation
  # leaves the start-up time along with it.
  export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
  # By default vLLM takes 90% of the video memory, and nothing is left for
  # layout detection.  But 0.75 is too little as well: ONNX Runtime holds an
  # arena of 5.41 GB (measured twice, with detector batch 4 and 64 -- the same
  # figure, the arena grows greedily and hardly depends on the batch), vLLM
  # takes 18.02 GB, together 23.43 of the card's 23.52 GB, and it is vLLM
  # itself that falls:
  #   torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 134.00 MiB
  # With PP-DocLayoutV2 the same 0.75 passed -- the V3 arena is simply bigger.
  # 0.60 leaves detection 9 GB.  The KV cache is then ~11 GB for a 0.9B model
  # -- still absurdly much, it will not become the bottleneck.
  # The port could still be held by the engine of a previous run.  fuser and ss
  # are absent from the image (neither `psmisc` nor `iproute2` is installed),
  # so there is nothing to find the holder of the port with -- we strike by
  # process name.  Our own shell is not touched by that: its command line
  # carries neither "vllm serve" nor "VLLM::".
  # NOTHING TO SEARCH WITH MEANS SAYING SO, NOT PRINTING "NO STRANGERS HERE".
  # `pgrep` was not in the image, and this line returned code 127 while the
  # `else` printed "no foreign vLLM processes on the machine" regardless of
  # the fact -- a speaking zero.
  #
  # AND THE GUARD IS NOT BELT AND BRACES: IT IS THE ONLY THING STANDING.
  # `infra/base/Dockerfile` installs `procps`, but the tag actually rented is
  # `BASE_IMAGE = ghcr.io/binarycat17/vast-base:d69de6e`, and that image was
  # built from a Dockerfile with eleven packages and neither `procps` nor
  # `git` -- both were added afterwards, in `ed4cb11`, and the image has not
  # been rebuilt or retagged since. So on a real rental this branch fires and
  # says so, which is right. To make the guard redundant, rebuild the image
  # and move `BASE_IMAGE` to the new tag.
  if ! command -v pgrep >/dev/null 2>&1; then
    log "NOTHING TO SEARCH WITH: the image has no pgrep -- whether foreign"
    log "vLLM processes are left cannot be told. This is NOT 'none left'."
    log "Rebuild the image (infra/base/Dockerfile installs procps)"
  else
    STALE=$(pgrep -f "vllm serve" 2>/dev/null | tr '\n' ' ')
    if [ -n "$STALE" ]; then
      log "vLLM processes left on the machine ($STALE) -- cleaning up"
      pkill -f "vllm serve" 2>/dev/null; pkill -f "VLLM::" 2>/dev/null
      sleep 3
      pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f "VLLM::" 2>/dev/null
      sleep 2
    else
      log "no foreign vLLM processes on the machine (pgrep was asked)"
    fi
  fi

  # setsid gives vLLM a process group of its own.  Without it the group is
  # shared with the script, and killing the group would have killed the script
  # itself -- exactly the trouble with exit code 144.
  setsid nohup vllm serve "$SERVE_MODEL" --trust-remote-code \
        --served-model-name "$MODEL" \
        --host 127.0.0.1 --port "$PORT" \
        --max-num-batched-tokens 16384 \
        --gpu-memory-utilization 0.60 \
        --no-enable-prefix-caching --mm-processor-cache-gb 0 \
        > "$OUT/vllm.log" 2>&1 &
  SRV=$!

  # The cleanup is in a trap rather than at the end: the script does not always
  # reach the end.  The `exit 1` path with a server that never came up went
  # past the cleanup, and a kill by timeout leaves not a line to run --
  # box.run() kills the local ssh client, and everything here dies of SIGPIPE
  # on tee.
  #
  # This became more important after setsid: an ssh break could once take the
  # server down by SIGHUP, now it is detached from the session on purpose, and
  # an orphan would be guaranteed rather than accidental.
  _cleaned=0
  cleanup() {
    [ "$_cleaned" = 1 ] && return; _cleaned=1
    if [ -n "${SRV:-}" ]; then
      # After setsid the PID equals the group id, so we strike the group and
      # take APIServer and EngineCore along with the parent.
      kill -- "-$SRV" 2>/dev/null || kill "$SRV" 2>/dev/null
      sleep 2
      kill -9 -- "-$SRV" 2>/dev/null
    fi
    # A sweep in case the group did not take everyone: EngineCore holds no
    # port socket and outlived both the parent and the freeing of the port.
    # Our own shell is not touched -- see the command lines above.
    pkill -9 -f "vllm serve" 2>/dev/null
    pkill -9 -f "VLLM::" 2>/dev/null
    return 0
  }
  trap cleanup EXIT INT TERM HUP

  for i in $(seq 1 600); do
      # Liveness is checked BEFORE curl: otherwise on the very first iteration
      # a FOREIGN server may answer, and we decide we raised ours.
      if ! kill -0 "$SRV" 2>/dev/null; then
          log "vLLM died at start, log tail:"; tail -40 "$OUT/vllm.log"; break
      fi
      if curl -sf "http://127.0.0.1:$PORT/v1/models" -o /dev/null 2>/dev/null; then
          SERVER_UP=1; log "vLLM came up in ${i}s"
          # Into the run ledger: the machine-picking model is tuned by this
          # number, because the warm-up rests on the host CPU.
          echo "{\"vllm_startup_s\": $i}" > "$OUT/vllm.json"
          break
      fi
      if ! kill -0 "$SRV" 2>/dev/null; then
          log "vLLM died at start, log tail:"; tail -40 "$OUT/vllm.log"; break
      fi
      sleep 1
  done
else
  log "vllm did not install -> there is nothing to compute with"
fi

# There used to be a fallback here to counting the VLM in-process.  It is
# impossible: our paddle is a CPU build (the GPU build pulls 3.69 GB and is not
# needed, detection moved to ONNX), while doc_vlm demands gpu:0 and falls with
# "PaddlePaddle is not compiled with CUDA".  Better to say so honestly and at
# once than to count 25 pages for that same error.
if [ "$SERVER_UP" = 0 ]; then
  log "vLLM did not come up -- nothing to compute with, leaving"
  log "=== vllm.log tail ==="; tail -60 "$OUT/vllm.log" 2>/dev/null
  exit 1
fi

SERVER_URL=""
[ "$SERVER_UP" = 1 ] && SERVER_URL="http://127.0.0.1:$PORT/v1"   # /v1 required

# ------------------------------------------------------------------ counting
log "=== parsing $(basename "$PDF") ==="
START=$(date +%s)
# The booksmith package arrives as an input file of the job and lies beside
# this script: at home and here ONE AND THE SAME code runs, not two editions.
RESUME_FLAG=""; [ "$RESUME" = "1" ] || RESUME_FLAG="--no-resume"
python "$WORK/entrypoint.py" --pkg "$WORK" --detect "$DETECT" \
       --pdf "$PDF" --out "$OUT" \
       --model "$MODEL" --server "$SERVER_URL" \
       --pages "$PAGES" --policy "$POLICY" $RESUME_FLAG
RC=$?
log "parsing finished with code $RC in $(( $(date +%s) - START ))s"

cleanup

[ "$RC" != 0 ] && { log "=== vllm.log tail ==="; tail -60 "$OUT/vllm.log" 2>/dev/null; }
log "=== exit ==="; du -sh "$OUT" 2>/dev/null
exit $RC
