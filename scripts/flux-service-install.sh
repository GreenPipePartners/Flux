#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/flux-stack.service"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$UNIT_DIR"

cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Flux local development stack
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/flux-start.sh
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=20

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable flux-stack.service

mkdir -p "$BIN_DIR"
ln -sfn "$ROOT_DIR/scripts/flux" "$BIN_DIR/flux"

printf 'Installed and enabled flux-stack.service\n'
printf 'Installed Flux CLI at %s/flux\n' "$BIN_DIR"
printf 'Start it with: %s/scripts/flux-service-start.sh\n' "$ROOT_DIR"
