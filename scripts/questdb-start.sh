#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUESTDB_VERSION="${QUESTDB_VERSION:-9.3.5}"
RUNTIME_DIR="${FLUX_RUNTIME_DIR:-$ROOT_DIR/.runtime}"
QUESTDB_DIST="${FLUX_QUESTDB_DIST:-$RUNTIME_DIR/questdb-dist}"
QUESTDB_DATA="${FLUX_QUESTDB_DATA:-$RUNTIME_DIR/questdb-data}"
QUESTDB_PORT="${QUESTDB_PORT:-8812}"
QUESTDB_HTTP_PORT="${QUESTDB_HTTP_PORT:-9000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

port_open() {
  "$PYTHON_BIN" - "$QUESTDB_PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
try:
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

if port_open; then
  printf 'QuestDB already listening on localhost:%s\n' "$QUESTDB_PORT"
  exit 0
fi

mkdir -p "$RUNTIME_DIR" "$QUESTDB_DIST" "$QUESTDB_DATA"

if [[ ! -x "$QUESTDB_DIST/questdb.sh" ]]; then
  archive="$RUNTIME_DIR/questdb-$QUESTDB_VERSION-no-jre-bin.tar.gz"
  url="https://github.com/questdb/questdb/releases/download/$QUESTDB_VERSION/questdb-$QUESTDB_VERSION-no-jre-bin.tar.gz"
  printf 'Downloading QuestDB %s...\n' "$QUESTDB_VERSION"
  curl -L "$url" -o "$archive"
  tar -xzf "$archive" -C "$QUESTDB_DIST" --strip-components=1
  chmod +x "$QUESTDB_DIST/questdb.sh"
fi

if [[ -z "${JAVA_HOME:-}" ]] && command -v java >/dev/null 2>&1; then
  java_bin="$(readlink -f "$(command -v java)")"
  export JAVA_HOME="$(dirname "$(dirname "$java_bin")")"
fi

printf 'Starting QuestDB at %s (PG wire localhost:%s, HTTP localhost:%s)...\n' "$QUESTDB_DATA" "$QUESTDB_PORT" "$QUESTDB_HTTP_PORT"
"$QUESTDB_DIST/questdb.sh" start -d "$QUESTDB_DATA"

printf 'Waiting for QuestDB PG wire on localhost:%s' "$QUESTDB_PORT"
for _ in $(seq 1 30); do
  if port_open; then
    printf '\n'
    exit 0
  fi
  printf '.'
  sleep 1
done

printf '\nTimed out waiting for QuestDB on localhost:%s\n' "$QUESTDB_PORT" >&2
exit 1
