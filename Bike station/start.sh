#!/usr/bin/env bash
# Starts SmartRack.  Usage:  bash start.sh
cd "$(dirname "$0")" || exit 1

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif python3 -c "import flask" 2>/dev/null; then
  PY=python3
else
  echo "Flask not found. Installing it once (needs internet)..."
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt || { echo "Setup failed. Is the Pi online?"; exit 1; }
  PY=.venv/bin/python
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "SmartRack is starting."
echo "  On this Pi:                 http://localhost:5000"
echo "  From phone/laptop (Wi-Fi):  http://${IP:-<pi-ip>}:5000"
exec $PY app.py
