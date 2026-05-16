#!/usr/bin/env bash
set -euo pipefail

systemctl --user --no-pager --full status flux-stack.service
