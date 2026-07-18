#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d "$VENV_DIR" ]; then
    echo "Создаю виртуальное окружение в $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "$SCRIPT_DIR/pyproject.toml" -nt "$VENV_DIR/.deps_installed" ]; then
    echo "Устанавливаю зависимости..."
    pip install --quiet --upgrade pip
    pip install --quiet -e "$SCRIPT_DIR"
    touch "$VENV_DIR/.deps_installed"
fi

exec comfygen "$@"
