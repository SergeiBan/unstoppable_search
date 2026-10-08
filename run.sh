#!/usr/bin/env bash
# Запуск игры одной командой. Окружение создаётся само, если его нет.
set -euo pipefail
cd "$(dirname "$0")"

export PATH="$HOME/.hermes/bin:$PATH"

if [ ! -x .venv/bin/python ]; then
    echo "Создаю окружение (.venv, Python 3.12 + pygame-ce)..."
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    uv pip install --python .venv/bin/python pip || true
    chmod +x .venv/bin/activate* 2>/dev/null || true
fi

exec .venv/bin/python src/main.py "$@"
