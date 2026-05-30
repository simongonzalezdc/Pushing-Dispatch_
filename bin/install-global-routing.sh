#!/usr/bin/env bash
# Install Pushing Dispatch as the shared model-routing command for local agents.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/pushing-dispatch" <<EOF
#!/usr/bin/env bash
set -euo pipefail

REPO="$REPO_ROOT"
export DISPATCH_MATRIX="\${DISPATCH_MATRIX:-\$REPO/dispatch_matrix.toml}"
exec python3 "\$REPO/cli.py" "\$@"
EOF

cat > "$BIN_DIR/dispatch" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

exec "$HOME/.local/bin/pushing-dispatch" "$@"
EOF

chmod +x "$BIN_DIR/pushing-dispatch" "$BIN_DIR/dispatch"

echo "Installed:"
echo "  $BIN_DIR/pushing-dispatch"
echo "  $BIN_DIR/dispatch"
echo ""
echo "Verify with:"
echo "  pushing-dispatch route --mode task --task 'fix a typo'"
