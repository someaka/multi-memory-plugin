#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# install.sh — one-command install for multi-memory plugin
# Usage:  ./scripts/install.sh          # default install
#         ./scripts/install.sh --test   # install + run tests
#         ./scripts/install.sh --help   # this message
#
# Symlinks the plugin into Hermes's plugin directory, validates
# the config, and optionally runs the test suite.
# Idempotent — safe to run multiple times.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_NAME="multi"
PLUGIN_SRC="$REPO_DIR/src/multi_memory"
PLUGIN_DST="$HERMES_HOME/hermes-agent/plugins/memory/$PLUGIN_NAME"
CONFIG_DST="$HERMES_HOME/config.yaml"
PYTHON="$(command -v python3 2>/dev/null || echo python3)"

# ── helpers ──────────────────────────────────────────────────
info()  { printf "\033[36m➜\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[33m⚠\033[0m %s\n" "$*" >&2; }
die()   { printf "\033[31m✘\033[0m %s\n" "$*" >&2; exit 1; }

# ── flags ────────────────────────────────────────────────────
RUN_TESTS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --test)  RUN_TESTS=true;  shift ;;
        --help)  sed -n '2,10p' "$0"; exit 0 ;;
        *)       die "Unknown flag: $1. Try --help." ;;
    esac
done

# ── main ─────────────────────────────────────────────────────
echo ""
info "multi-memory plugin installer v0.7.0"
echo ""

# 1. Verify source exists
if [[ ! -d "$PLUGIN_SRC" ]]; then
    die "Source not found: $PLUGIN_SRC"
fi
ok "Source directory found"

# 2. Create plugin destination directory
mkdir -p "$(dirname "$PLUGIN_DST")"

# 3. Create/verify symlink for memory provider discovery (idempotent)
if [[ -L "$PLUGIN_DST" ]]; then
    EXISTING="$(readlink "$PLUGIN_DST")"
    if [[ "$EXISTING" == "$PLUGIN_SRC" ]]; then
        ok "Memory symlink already points to source (idempotent)"
    else
        warn "Memory symlink points elsewhere ($EXISTING) — updating"
        ln -sfn "$PLUGIN_SRC" "$PLUGIN_DST"
        ok "Memory symlink updated"
    fi
elif [[ -d "$PLUGIN_DST" ]]; then
    warn "Directory exists at $PLUGIN_DST — not a symlink; leaving it"
else
    ln -s "$PLUGIN_SRC" "$PLUGIN_DST"
    ok "Memory symlink created: $PLUGIN_DST → $PLUGIN_SRC"
fi

# 3b. Create symlink for general plugin scanner (CLI commands, dashboard)
PLUGIN_GENERAL_DST="$HERMES_HOME/plugins/$PLUGIN_NAME"
mkdir -p "$HERMES_HOME/plugins"
if [[ -L "$PLUGIN_GENERAL_DST" ]]; then
    EXISTING="$(readlink "$PLUGIN_GENERAL_DST")"
    if [[ "$EXISTING" == "$PLUGIN_SRC" ]]; then
        ok "General plugin symlink already points to source (idempotent)"
    else
        warn "General plugin symlink points elsewhere ($EXISTING) — updating"
        ln -sfn "$PLUGIN_SRC" "$PLUGIN_GENERAL_DST"
        ok "General plugin symlink updated"
    fi
elif [[ -d "$PLUGIN_GENERAL_DST" ]]; then
    warn "Directory exists at $PLUGIN_GENERAL_DST — not a symlink; leaving it"
else
    ln -s "$PLUGIN_SRC" "$PLUGIN_GENERAL_DST"
    ok "General plugin symlink created: $PLUGIN_GENERAL_DST → $PLUGIN_SRC"
fi

# 4. Validate Python import
if python3 -c "import sys; sys.path.insert(0, '$REPO_DIR/src'); from multi_memory import MultiMemoryProvider; print(f'OK: {MultiMemoryProvider.__new__(MultiMemoryProvider).name}')" 2>/dev/null; then
    ok "Plugin imports successfully"
else
    die "Plugin import failed — is the repo installed as a package?"
fi

# 5. Check plugin.yaml
if [[ -f "$REPO_DIR/plugin.yaml" ]]; then
    ok "plugin.yaml found"
else
    warn "plugin.yaml missing — Hermes plugin loader may not discover this plugin"
fi

# 6. Check config.yaml
if [[ -f "$CONFIG_DST" ]]; then
    ok "Config file found at $CONFIG_DST"
else
    warn "No config.yaml at $CONFIG_DST — plugin loads at runtime but will use defaults"
fi

# 7. Auto-enable plugin (so it appears in hermes plugins list / dashboard)
if command -v hermes &>/dev/null; then
    if hermes plugins enable multi 2>/dev/null; then
        ok "Plugin enabled"
    else
        warn "Could not auto-enable plugin — run 'hermes plugins enable multi' manually"
    fi
else
    warn "hermes CLI not found — run 'hermes plugins enable multi' manually"
fi

# 8. Auto-configure memory.provider if not already set to 'multi'
if [[ -f "$CONFIG_DST" ]]; then
    CURRENT_PROVIDER="$("$PYTHON" -c "
import yaml
with open('$CONFIG_DST') as f:
    cfg = yaml.safe_load(f) or {}
print(cfg.get('memory', {}).get('provider', ''))
" 2>/dev/null || echo "")"
    if [[ "$CURRENT_PROVIDER" != "multi" ]]; then
        if hermes config set memory.provider multi 2>/dev/null; then
            ok "memory.provider configured"
        else
            warn "Could not auto-configure memory.provider — set it manually"
        fi
    else
        ok "memory.provider already set to multi"
    fi
else
    warn "Config file not found — set memory.provider manually"
fi

# 9. Run tests (optional)
if $RUN_TESTS; then
    echo ""
    info "Running tests…"
    cd "$REPO_DIR"
    if "$PYTHON" -m pytest tests/ -v; then
        ok "All tests passed"
    else
        die "Some tests failed — see output above"
    fi
fi

echo ""
ok "Install complete"
echo ""
info "Next steps:"
echo "   1. Add backends: hermes multi add <name> (e.g. hermes multi add mnemosyne)"
echo "   2. Check status:  hermes multi status"
echo "   3. See CONFIG.md for full backend reference"
echo ""
