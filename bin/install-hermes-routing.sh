#!/usr/bin/env bash
# Install Liam/Hermes's explicit Dispatch adapter, skill, and native provider boundary.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_PYTHON="${HERMES_PYTHON:-$HERMES_HOME/hermes-agent/venv/bin/python}"

if [[ ! -x "$HERMES_PYTHON" ]]; then
  HERMES_PYTHON="$(command -v python3)"
fi
if ! "$HERMES_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
  echo "Hermes routing setup requires PyYAML in $HERMES_PYTHON" >&2
  exit 69
fi

"$HERMES_PYTHON" "$SCRIPT_DIR/configure-hermes-routing.py" --config "$HERMES_HOME/config.yaml"
mkdir -p "$HOME/.local/bin" "$HERMES_HOME/skills/pushing-dispatch"
ln -sfn "$SCRIPT_DIR/hermes-dispatch" "$HOME/.local/bin/hermes-dispatch"
cp "$REPO_ROOT/integrations/hermes/SKILL.md" "$HERMES_HOME/skills/pushing-dispatch/SKILL.md"
chmod 600 "$HERMES_HOME/skills/pushing-dispatch/SKILL.md"

echo "Installed Hermes Dispatch adapter and skill."
echo "Restart Hermes gateway/serve processes to load the updated configuration."
