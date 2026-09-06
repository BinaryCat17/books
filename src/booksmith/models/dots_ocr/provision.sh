#!/usr/bin/env bash
# Provisioning for dots.ocr. The image carries delivery only; everything
# heavy is installed here: a measurement on the previous job showed docker
# uses five percent of the channel, while uv and hf use nearly all of it.
#
# The script is idempotent: on a warm machine it finishes in seconds.
set -euo pipefail
ENVDIR=${ENVDIR:-/opt/env}
MODELS=${MODELS:-/models}
export UV_LINK_MODE=copy UV_HTTP_TIMEOUT=180 HF_HUB_DISABLE_PROGRESS_BARS=1
export HF_HOME=${HF_HOME:-$MODELS/hf}

step() { local l="$1"; shift; local t0=$(date +%s); "$@"; local t1=$(date +%s)
         printf '== %-16s %4ds\n' "$l" "$((t1-t0))"; }

step "python"    uv python install 3.12
step "venv"      uv venv "$ENVDIR" --python 3.12 --allow-existing
export VIRTUAL_ENV="$ENVDIR"
# torch on a line of its own and from the cu124 index: the general index
# delivers a build for a different CUDA, and that fails on the card -- which
# is to say, for money.
step "torch"  uv pip install --python "$ENVDIR/bin/python" \
  --index-url https://download.pytorch.org/whl/cu124 torch torchvision
# transformers IS PINNED. Newer processor versions hand over the key
# `mm_token_type_ids`, which the dots.ocr remote code does not accept, and the
# run dies with ValueError on the first page -- that cost three rentals. The
# version is the one contemporary with the model itself (October 2025).
step "wheels" uv pip install --python "$ENVDIR/bin/python" \
  "transformers==4.51.3" accelerate qwen-vl-utils pymupdf pillow einops \
  huggingface_hub
# Weights are pulled AHEAD and as a step of their own: otherwise their time
# dissolves into the run, and "the model is slow" cannot be told apart from
# "the weights took ten minutes to arrive".
#
# They go into a directory with NO DOT IN ITS NAME. The transformers remote-
# code loader turns the path into a package name, and the dot in "dots.ocr"
# becomes a separator: the relative import inside the model dies with
# "No module named transformers_modules.rednote-hilab.dots". That cost a
# rental. The model card warns of the same thing.
export DOTS_DIR="$MODELS/DotsOCR"
step "weights" "$ENVDIR/bin/python" - <<PY
import os
from huggingface_hub import snapshot_download
p = snapshot_download("rednote-hilab/dots.ocr",
                      local_dir=os.environ["DOTS_DIR"])
print("weights in", p, flush=True)
PY
"$ENVDIR/bin/python" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
