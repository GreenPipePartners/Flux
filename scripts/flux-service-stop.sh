#!/usr/bin/env bash
set -euo pipefail

systemctl --user stop flux-stack.service
systemctl --user --no-pager --full status flux-stack.service || true
