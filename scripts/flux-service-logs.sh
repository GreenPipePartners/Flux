#!/usr/bin/env bash
set -euo pipefail

journalctl --user -u flux-stack.service -f
