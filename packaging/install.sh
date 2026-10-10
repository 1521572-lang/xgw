#!/bin/sh
# Установка XGW из каталога репозитория: sudo sh packaging/install.sh [--yes]
# Вся логика — в `xgw install` (Python); здесь только запуск из исходников.
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo "ошибка: нужен python3" >&2
    exit 1
fi
PYTHONPATH="$here/src" exec python3 -P -m xgw install "$@"
