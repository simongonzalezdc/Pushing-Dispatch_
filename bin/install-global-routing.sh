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

python_is_supported() {
  "\$1" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1
}

for candidate in "\${DISPATCH_PYTHON:-}" /opt/homebrew/bin/python3 /usr/local/bin/python3 "\$(command -v python3 2>/dev/null || true)"; do
  if [[ -n "\$candidate" && -x "\$candidate" ]] && python_is_supported "\$candidate"; then
    exec "\$candidate" "\$REPO/cli.py" "\$@"
  fi
done

echo "pushing-dispatch requires Python 3.10 or newer" >&2
exit 69
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
