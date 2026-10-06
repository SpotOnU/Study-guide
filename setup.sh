#!/bin/bash
# One-time setup: creates a private Python environment in .venv and installs
# what the app needs. Safe to run again (e.g. after pulling updates).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/macos/ and try again."
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "Python 3.9 or newer is required (found $("$PYTHON" --version))."
  echo "Install a newer one from https://www.python.org/downloads/macos/"
  exit 1
fi

"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements-dev.txt
echo
echo "Setup complete. Start the app with:  ./run.sh"
