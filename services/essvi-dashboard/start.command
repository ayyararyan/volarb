#!/bin/zsh
set -eu
cd -- "${0:A:h}"
exec "${ESSVI_PYTHON:-$HOME/Documents/Shaurya/research/.venv/bin/python}" run.py "$@"
