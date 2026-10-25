#!/usr/bin/env sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"
python3 -m unittest discover -s tests -v
python3 -m compileall -q cairo tests

if command -v node >/dev/null 2>&1; then node tests/test_voice.cjs; fi
