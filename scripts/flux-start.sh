#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web/Flux"
FIELD_CONFIG="$WEB_DIR/field/field-config.json"
FIELD_PROJECT="$ROOT_DIR/field/Flux.FieldAgent/Flux.FieldAgent.csproj"

pids=()

cleanup() {
  if ((${#pids[@]})); then
    printf '\nStopping Flux services...\n'
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}

start_service() {
  local name="$1"
  shift

  "$@" 2>&1 | sed -u "s/^/[$name] /" &
  pids+=("$!")
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local attempts=60

  printf 'Waiting for %s at %s' "$name" "$url"
  for _ in $(seq 1 "$attempts"); do
    if curl --silent --fail --output /dev/null "$url"; then
      printf '\n'
      return 0
    fi
    printf '.'
    sleep 1
  done

  printf '\nTimed out waiting for %s at %s\n' "$name" "$url" >&2
  return 1
}

trap cleanup EXIT INT TERM

printf 'Preparing Flux database and FieldAgent config...\n'
(
  cd "$WEB_DIR"
  uv run python manage.py migrate
  uv run python manage.py repair_sequences base
  uv run python manage.py export_field_config --output field/field-config.json
)

printf 'Starting Flux stack...\n'
start_service "django" bash -lc "cd '$WEB_DIR' && uv run python manage.py runserver --noreload -6 '[::]:8000'"
wait_for_url "http://localhost:8000/" "Django"
start_service "field" dotnet run --project "$FIELD_PROJECT" --FluxField:ConfigPath="$FIELD_CONFIG"
start_service "demo" bash -lc "cd '$WEB_DIR' && uv run python manage.py run_sim_demo"

printf '\nFlux stack is running. Open http://localhost:8000/live/ or http://localhost:8000/sim/.\n'
printf 'Press Ctrl-C to stop all Flux services.\n\n'

set +e
wait -n "${pids[@]}"
status=$?
set -e

printf '\nA Flux service exited with status %s. Shutting down the rest.\n' "$status"
exit "$status"
