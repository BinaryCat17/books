#!/usr/bin/env bash
# The container's entry: CUDA_HOME for the kernels vLLM compiles on the fly,
# found in place because the layout of the NVIDIA wheels has moved once
# already, then the shim, which raises vLLM itself and kills it as a group.
set -uo pipefail
NVCC=$(find /opt/env -type f -name nvcc -perm -u+x 2>/dev/null | head -1)
if [ -n "$NVCC" ]; then
  export CUDA_HOME="$(dirname "$(dirname "$NVCC")")"
  export PATH="$CUDA_HOME/bin:$PATH"
fi
exec books serve vlm --host 0.0.0.0 --port 8000 --log-dir /var/log "$@"
