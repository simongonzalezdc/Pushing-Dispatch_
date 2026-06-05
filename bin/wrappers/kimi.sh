#!/usr/bin/env bash
# kimi.sh - Alias wrapper for Kimi executors.
#
# Delegates to kimi-cli.sh (the local Kimi Code CLI OAuth wrapper).
# Exists so the wrapper name aligns with the executor key in dispatch_matrix.toml.

set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/kimi-cli.sh" "$@"
