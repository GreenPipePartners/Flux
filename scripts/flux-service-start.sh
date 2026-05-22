#!/usr/bin/env bash
set -euo pipefail

FLUX_WEB_MODE="${FLUX_WEB_MODE:-gunicorn}"

case "$FLUX_WEB_MODE" in
  gunicorn|dev|internal)
    ;;
  *)
    printf 'Unsupported FLUX_WEB_MODE=%s. Use gunicorn, dev, or internal.\n' "$FLUX_WEB_MODE" >&2
    exit 2
    ;;
esac

systemctl --user set-environment FLUX_WEB_MODE="$FLUX_WEB_MODE"
systemctl --user start flux-stack.service
systemctl --user --no-pager --full status flux-stack.service
