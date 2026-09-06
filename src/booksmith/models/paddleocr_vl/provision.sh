#!/usr/bin/env bash
# Provisioning on the rented machine -- what used to be image layers.
#
# Why not layers: docker pulls three layers at once, one stream per layer,
# and the registry throttles a connection to ~25 Mbit/s -- a 76 Mbit/s ceiling
# whatever the machine's channel is. Measured: 6.02 GB of image took 10.7
# minutes. uv and hf open dozens of connections; the same 11 GB install in 82
# seconds, nearly saturating a 1500 Mbit/s link.
#
# The script is idempotent: on a warm machine (--reuse) everything is already
# there and it finishes in seconds. Each step prints its own time, so that
# "the start is slow" always resolves to a particular step.
set -euo pipefail

ENVDIR=${ENVDIR:-/opt/env}
MODELS=${MODELS:-/models}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export UV_LINK_MODE=copy
export UV_HTTP_TIMEOUT=180
export HF_HUB_DISABLE_PROGRESS_BARS=1

step() {
    local label="$1"; shift
    local t0 t1
    t0=$(date +%s)
    "$@"
    t1=$(date +%s)
    printf '== %-18s %4ds\n' "$label" "$((t1 - t0))"
}

step "python" uv python install 3.12
# --allow-existing is mandatory: on a warm machine (--reuse, or the same
# machine under the same tag) the directory is already there, and without the
# flag uv dies with "A virtual environment already exists at: /opt/env" --
# on exactly the scenario the script was made idempotent for.
step "venv"      uv venv "$ENVDIR" --python 3.12 --allow-existing

export VIRTUAL_ENV="$ENVDIR"
export PATH="$ENVDIR/bin:$PATH"

# constraints.txt is what gets installed -- the whole pinned tree, not the
# top level: otherwise dependency resolution happens here, on a card that
# bills, and a fresh release of any transitive dependency drops the book
# halfway. requirements.in stays the input for rebuilding this file; see its
# header.
#
# --torch-backend=cu130 is needed here too: the version is pinned as
# 2.13.0+cu130, and there is no such thing on PyPI -- it lives in the pytorch
# index.
step "wheels" uv pip install -r "$HERE/constraints.txt" --torch-backend=cu130

# THE 1.6 REPOSITORY, NOT PLAIN PaddleOCR-VL. This once said
# `PaddlePaddle/PaddleOCR-VL` -- DIFFERENT, older weights -- while the knob
# `MODEL_NAME` declares `PaddleOCR-VL-1.6-0.9B`, and `vllm serve
# --served-model-name` makes the server call itself whatever it is told. The
# run would have come out successful and wrong: the snapshot would name a
# version it did not compute with, and the model-name check could not catch
# that by construction -- it proves we reached OUR server, not which weights
# are under it. Only the reader fingerprint taken beside them proves that
# (sha256 of config.json, `models/paddleocr_vl/reader.py`).
VL_REPO="${VL_REPO:-PaddlePaddle/PaddleOCR-VL-1.6}"
step "VL weights" hf download "$VL_REPO" --local-dir "$MODELS/vl"
# WHERE THE WEIGHTS CAME FROM -- in a file beside them, not in the shell's
# memory. Without it there is nothing to prove the version with: `config.json`
# is BYTE-IDENTICAL between 1.6 and the old `PaddleOCR-VL` (sha256 ce7f4565…,
# 2059 bytes), so the guard that hashed it could not catch the very run it was
# written for. `tokenizer_config.json`, `chat_template.jinja` and
# `preprocessor_config.json` do differ -- but writing the name down beats
# guessing from them.
printf '{"repo": "%s"}\n' "$VL_REPO" > "$MODELS/vl/SOURCE.json"
# THE DETECTOR WEIGHTS ARE NO LONGER PULLED, and that is 214 MB per run.
# Detection happens AT HOME, on the CPU and free, and what arrives on the box
# is a finished `detect/` directory -- boxes, labels, order. A step from the
# earlier job, when layout was computed on the card, lived here: `hf download
# PaddlePaddle/PP-DocLayoutV2_onnx --local-dir /models/layout`. No consumer of
# those weights comes up on the box -- nobody reads `LAYOUT_MODEL_DIR`, and
# `books read` never calls the detector at all.
