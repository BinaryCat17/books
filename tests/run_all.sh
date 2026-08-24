#!/usr/bin/env bash
# Вся приёмка одной командой. Код 1, если упал хоть один набор.
PY=/home/smirn/books/.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" "$(dirname "$0")/run_all.py" "$@"
