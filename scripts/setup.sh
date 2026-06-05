#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# setup.sh — interactive setup wizard for multi-memory plugin
#
# Discovers available backends, presents a checkbox-style UI,
# and writes the chosen config to config.yaml.
# Handles missing backends gracefully (graceful skip, not crash).
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CONFIG_FILE="$HERMES_HOME/config.yaml"

# ── helpers ──────────────────────────────────────────────────
info()  { printf "\033[36m➜\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[33m⚠\033[0m %s\n" "$*" >&2; }
die()   { printf "\033[31m✘\033[0m %s\n" "$*" >&2; exit 1; }

prompt_yn() {
    local msg="$1" default="${2:-y}" ans
    read -r -p "$msg (y/n) [$default]: " ans
    case "${ans:-$default}" in
        y|Y) return 0 ;;
        *)   return 1 ;;
    esac
}

# ── backend definitions ──────────────────────────────────────
# Order matters for display
BACKEND_NAMES=(Mnemosyne Mem0 Holographic Honcho)
declare -A BACKEND_KEY BACKEND_DEPS BACKEND_STDLIB BACKEND_MODULE

BACKEND_KEY[Mnemosyne]="mnemosyne"
BACKEND_DEPS[Mnemosyne]="plugin (github.com/AxDSan/mnemosyne)"
BACKEND_STDLIB[Mnemosyne]="plugin"
BACKEND_MODULE[Mnemosyne]="mnemosyne"

BACKEND_KEY[Mem0]="mem0"
BACKEND_DEPS[Mem0]="pip install mem0ai"
BACKEND_STDLIB[Mem0]="false"
BACKEND_MODULE[Mem0]="plugins.memory.mem0"

BACKEND_KEY[Holographic]="holographic"
BACKEND_DEPS[Holographic]="stdlib-only (no pip)"
BACKEND_STDLIB[Holographic]="true"
BACKEND_MODULE[Holographic]="plugins.memory.holographic"

BACKEND_KEY[Honcho]="honcho"
BACKEND_DEPS[Honcho]="pip install honcho-ai"
BACKEND_STDLIB[Honcho]="false"
BACKEND_MODULE[Honcho]="plugins.memory.honcho"

# ── check python ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    die "python3 not found — Python 3.10+ required"
fi
PYTHON="$(command -v python3)"

# ── detect backends ──────────────────────────────────────────
detect_backend() {
    local label="$1" key="${BACKEND_KEY[$label]}" mod="${BACKEND_MODULE[$label]}" stdlib="${BACKEND_STDLIB[$label]}"
    if [[ "$stdlib" == "plugin" ]]; then
        # User-installed plugin — check if directory exists
        local plugin_dir="$HERMES_HOME/plugins/$key"
        [[ -d "$plugin_dir" && -f "$plugin_dir/__init__.py" ]]
        return $?
    fi
    if [[ "$stdlib" == "true" ]]; then
        # stdlib-only backends (holographic) are always available
        return 0
    fi
    # Check if the top-level module can be imported
    local top_module="${mod%%.*}"
    "$PYTHON" -c "import $top_module" 2>/dev/null
}

# ── main ─────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   multi-memory plugin — setup wizard v0.7.0  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
info "Python: $("$PYTHON" --version 2>&1)"
echo ""

# Phase 1: detect what's installed
INSTALLED=()
MISSING=()
for label in "${BACKEND_NAMES[@]}"; do
    if detect_backend "$label"; then
        INSTALLED+=("$label")
        ok "${label} (${BACKEND_KEY[$label]}) — available"
    else
        MISSING+=("$label")
        warn "${label} (${BACKEND_KEY[$label]}) — ${BACKEND_DEPS[$label]}"
    fi
done

if [[ ${#INSTALLED[@]} -eq 0 ]]; then
    echo ""
    die "No backends detected! Install at least one: mnemosyne is stdlib-only and should always work."
fi

# Phase 2: handle missing backends gracefully
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo ""
    warn "Some backends are not installed (see ⚠ above)."
    info "You can enable them later after installing the required packages."
    if ! prompt_yn "Continue with only the available backends?" "y"; then
        info "Install missing packages and re-run setup.sh"
        exit 0
    fi
fi

# Phase 3: confirm selection
echo ""
info "Backends to enable:"
for label in "${INSTALLED[@]}"; do
    printf "   \033[32m✔\033[0m %s (%s)\n" "$label" "${BACKEND_KEY[$label]}"
done

echo ""
if ! prompt_yn "Write config?" "y"; then
    info "Setup cancelled — no changes made."
    exit 0
fi

# Phase 4: build YAML and write
mkdir -p "$(dirname "$CONFIG_FILE")"

# Build backend entries
BACKEND_BLOCK=""
for label in "${INSTALLED[@]}"; do
    BACKEND_BLOCK="$BACKEND_BLOCK
      ${BACKEND_KEY[$label]}: {}"
done

YAML_BLOCK="memory:
  provider: multi
  multi:
    backends:$BACKEND_BLOCK"

if [[ -f "$CONFIG_FILE" ]]; then
    if grep -q "^memory:" "$CONFIG_FILE" 2>/dev/null; then
        warn "Config already has a 'memory:' section."
        if prompt_yn "Replace it with the generated multi-memory config?" "n"; then
            # Use Python for safe YAML manipulation via heredoc
            "$PYTHON" << PYEOF
import yaml

config_path = "$CONFIG_FILE"
with open(config_path) as f:
    cfg = yaml.safe_load(f) or {}

installed = ${INSTALLED[@]@Q}
key_map = {
    "Mnemosyne": "mnemosyne",
    "Mem0": "mem0",
    "Holographic": "holographic",
    "Honcho": "honcho",
}

backends = {key_map[n]: {} for n in installed if n in key_map}
cfg["memory"] = {
    "provider": "multi",
    "multi": {
        "backends": backends,
    },
}

with open(config_path, "w") as f:
    yaml.dump(cfg, f, default_flow_style=False, indent=2)

print(f"Updated {config_path}: {len(backends)} backend(s) configured")
PYEOF
            ok "Config updated: $CONFIG_FILE"
        else
            info "Config not modified."
        fi
    else
        # Append to existing config
        echo "" >> "$CONFIG_FILE"
        echo "$YAML_BLOCK" >> "$CONFIG_FILE"
        ok "Config appended to $CONFIG_FILE"
    fi
else
    {
        echo "# Hermes Agent configuration"
        echo "# Generated by multi-memory setup.sh"
        echo ""
        echo "$YAML_BLOCK"
    } > "$CONFIG_FILE"
    ok "Config created at $CONFIG_FILE"
fi

# Phase 5: validate
echo ""
info "Validating configuration…"
if "$PYTHON" -c "
import sys
sys.path.insert(0, '$REPO_DIR/src')
import os, yaml
from multi_memory import _load_backends_from_config

home = os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes'))
p = os.path.join(home, 'config.yaml')
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
subs = _load_backends_from_config(cfg)
print(f'  Loaded {len(subs)} backend(s): {[s.name for s in subs]}')
" 2>&1; then
    ok "Configuration is valid"
else
    warn "Validation failed — check $CONFIG_FILE manually"
fi

echo ""
ok "Setup complete!"
echo ""
info "Next steps:"
echo "  1. cd $REPO_DIR"
echo "  2. python -m pytest tests/ -v    (run tests)"
echo "  3. hermes gateway restart         (restart Hermes)"
echo ""
