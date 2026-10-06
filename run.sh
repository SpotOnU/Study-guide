#!/bin/bash
# Start Study Guide.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Please run ./setup.sh first."
  exit 1
fi
exec .venv/bin/python -m studyguide
