#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web/Flux"
FIELD_CONFIG="$WEB_DIR/field/field-config.json"
FIELD_PROJECT="$ROOT_DIR/field/Flux.FieldAgent/Flux.FieldAgent.csproj"
FIELD_RUNTIME_DIR="$ROOT_DIR/.runtime/field-agent"
FLUX_FIELD_AGENT_MODE="${FLUX_FIELD_AGENT_MODE:-supervised}"
FLUX_WEB_MODE="${FLUX_WEB_MODE:-gunicorn}"
FLUX_WEB_WORKERS="${FLUX_WEB_WORKERS:-8}"
FLUX_WEB_THREADS="${FLUX_WEB_THREADS:-2}"
FLUX_SAMPLER_INTERVAL="${FLUX_SAMPLER_INTERVAL:-5}"
FLUX_SAMPLER_BATCH_SIZE="${FLUX_SAMPLER_BATCH_SIZE:-100}"

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

case "$FLUX_FIELD_AGENT_MODE" in
  legacy|supervised)
    ;;
  *)
    printf 'Unsupported FLUX_FIELD_AGENT_MODE=%s. Use legacy or supervised.\n' "$FLUX_FIELD_AGENT_MODE" >&2
    exit 2
    ;;
esac

case "$FLUX_WEB_MODE" in
  gunicorn|dev|internal)
    ;;
  *)
    printf 'Unsupported FLUX_WEB_MODE=%s. Use gunicorn, dev, or internal.\n' "$FLUX_WEB_MODE" >&2
    exit 2
    ;;
esac

printf 'Preparing Flux database and FieldAgent config...\n'
(
  cd "$WEB_DIR"
  uv run python manage.py migrate
  uv run python manage.py repair_sequences base
  uv run python manage.py install_fluxolot_fishtank --history-days "${FLUXOLOT_HISTORY_DAYS:-30}" --history-interval-minutes "${FLUXOLOT_HISTORY_INTERVAL_MINUTES:-60}"
  if [[ "$FLUX_FIELD_AGENT_MODE" == "legacy" ]]; then
    uv run python manage.py export_field_config --output field/field-config.json
  fi
)

printf 'Starting Flux stack with FLUX_WEB_MODE=%s...\n' "$FLUX_WEB_MODE"
"$ROOT_DIR/scripts/questdb-start.sh"
if [[ "$FLUX_WEB_MODE" == "gunicorn" ]]; then
  start_service "django" bash -lc "cd '$WEB_DIR' && PYTHONPATH='src:$ROOT_DIR' uv run gunicorn flux.wsgi:application --bind='0.0.0.0:8000' --workers='$FLUX_WEB_WORKERS' --threads='$FLUX_WEB_THREADS' --timeout=120"
else
  start_service "django" bash -lc "cd '$WEB_DIR' && PYTHONPATH='src:$ROOT_DIR' uv run python manage.py runserver 0.0.0.0:8000"
fi
wait_for_url "http://localhost:8000/" "Django"
start_service "docs" bash -lc "cd '$ROOT_DIR' && uv run --project '$WEB_DIR' mkdocs serve --dev-addr='127.0.0.1:8001'"
wait_for_url "http://localhost:8001/" "Flux docs"
if [[ "$FLUX_FIELD_AGENT_MODE" == "supervised" ]]; then
  start_service "field-supervisor" bash -lc "cd '$WEB_DIR' && PYTHONPATH='src:$ROOT_DIR' uv run python manage.py flux_field_supervisor --runtime-dir '$FIELD_RUNTIME_DIR' --project-path '$FIELD_PROJECT'"
else
  start_service "field" dotnet run --project "$FIELD_PROJECT" --FluxField:ConfigPath="$FIELD_CONFIG"
fi
start_service "serve-monitor" bash -lc "cd '$WEB_DIR' && PYTHONPATH='src:$ROOT_DIR' uv run python manage.py flux_serve_monitor"
start_service "fluxolot-sampler" bash -lc "cd '$WEB_DIR' && PYTHONPATH='src:$ROOT_DIR' uv run python manage.py flux_sampling_worker --profile fluxolot-fishtank --interval '$FLUX_SAMPLER_INTERVAL' --batch-size '$FLUX_SAMPLER_BATCH_SIZE'"

printf '\nFlux stack is running. Open http://localhost:8000/live/, http://localhost:8000/sim/, or http://localhost:8001/.\n'
printf 'Press Ctrl-C to stop all Flux services.\n\n'

set +e
wait -n "${pids[@]}"
status=$?
set -e

printf '\nA Flux service exited with status %s. Shutting down the rest.\n' "$status"
exit "$status"
