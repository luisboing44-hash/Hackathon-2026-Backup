#!/usr/bin/env bash
# Makes SmartRack start by itself whenever the Pi boots.  Usage:  bash install_service.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$DIR/.venv/bin/python" ]; then PY="$DIR/.venv/bin/python"; else PY="$(command -v python3)"; fi
if ! "$PY" -c "import flask" 2>/dev/null; then echo "Run 'bash start.sh' once first (it installs Flask), then press Ctrl+C and run this again."; exit 1; fi
sudo tee /etc/systemd/system/smartrack.service >/dev/null <<EOF
[Unit]
Description=SmartRack bike parking
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$PY $DIR/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now smartrack
echo "Done. SmartRack now starts on boot.  Check with: sudo systemctl status smartrack"
