#!/usr/bin/env bash
set -euo pipefail

export PATH=/opt/rocm/bin:$PATH
export HSA_OVERRIDE_GFX_VERSION=11.5.1
export LD_LIBRARY_PATH=/srv/external/llama.cpp-b9611/build/bin:/opt/rocm/lib

cd /srv/external/llama.cpp-b9611/build/bin
exec ./llama-server \
  -m /srv/external/models/gguf/Qwen3.5/Qwen3.5-35B-A3B-Q4_K_M.gguf \
  -ngl 99 -c 32768 -np 1 --fit off --no-repack --port 8902 --host 0.0.0.0 \
  -t 8 -tb 8 -b 512 -ub 128 \
  -fa on --reasoning off
