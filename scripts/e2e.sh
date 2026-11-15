#!/usr/bin/env bash
# Run the Playwright suite against a real, freshly prepared stack. Used verbatim by CI and locally.
#
#   E2E_DATABASE_URL=postgresql://user@localhost:5433/opportunity_hub_e2e scripts/e2e.sh [playwright args]
#
# Steps: refuse anything but a local throwaway database, migrate it to head, seed the real demo dataset
# (through the validated publish path), create the e2e admin account, start the API and the Vite dev
# server, run Playwright.
#
# Security controls stay on: the per-account credential limit is set explicitly (10/min, the
# production default) and CLIENT_IP_STRATEGY=none mirrors render.yaml. Email delivery stays disabled.
#
# Target safety: backend/scripts/seed_e2e_fixtures.py --check-only must accept the database (name with
# an "e2e"/"test" word, loopback host or local socket, APP_ENV not production) before anything runs.
#
# Process cleanup: the API, Vite and Playwright each run in their own session (setsid). On exit,
# failure, Ctrl-C or SIGTERM the script records every process in those groups and all their
# descendants (Playwright starts Chromium in a session of its own, so the groups alone don't cover
# it), sends TERM, then KILL, and fails if any recorded process survives or if anything still listens
# on its ports over IPv4 or IPv6 loopback.
#
# Logs go to $E2E_ARTIFACTS (default frontend/e2e-artifacts): request paths and statuses only; this
# script prints no credentials or tokens.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${E2E_DATABASE_URL:?set E2E_DATABASE_URL to a throwaway local database}"
ARTIFACTS="${E2E_ARTIFACTS:-$ROOT/frontend/e2e-artifacts}"
API_PORT="${E2E_API_PORT:-8000}"
WEB_PORT="${E2E_WEB_PORT:-5173}"
PYTHON="${E2E_PYTHON:-python}"

mkdir -p "$ARTIFACTS"
export DATABASE_URL="$E2E_DATABASE_URL"
export APP_ENV=development
export APP_ENV_FILE=""  # never pick up a developer's backend/.env
export JWT_SECRET="${JWT_SECRET:-e2e-only-jwt-secret-not-used-anywhere-else}"
export AUTH_RATE_LIMIT_PER_MINUTE=10
export CLIENT_IP_STRATEGY=none
export EMAIL_DELIVERY=disabled
unset TRUSTED_PROXY_CIDRS CLIENT_IP_HEADER RENDER

groups=()   # process-group ids of everything started in the background
tracked=()  # every process in those groups and all descendants, recorded at cleanup

port_in_use() {  # port: true if anything accepts connections on IPv4 or IPv6 loopback
  local host
  for host in 127.0.0.1 ::1; do
    (exec 3<>"/dev/tcp/$host/$1") 2>/dev/null && return 0
  done
  return 1
}

signal_group() {  # signal, pgid: the whole group; the leader alone if setsid hasn't run yet
  kill "-$1" -- "-$2" 2>/dev/null || kill "-$1" "$2" 2>/dev/null || true
}

group_alive() {
  kill -0 -- "-$1" 2>/dev/null || kill -0 "$1" 2>/dev/null
}

alive() {  # pid: running (a zombie awaiting its parent does not count)
  local state
  state="$(ps -o stat= -p "$1" 2>/dev/null)" && [[ "$state" != Z* ]]
}

process_tree() {  # pids...: each pid and all its descendants
  local pid
  for pid in "$@"; do
    echo "$pid"
    process_tree $(pgrep -P "$pid" || true)
  done
}

stop_all() {
  local pgid pid
  for pgid in "${groups[@]}"; do
    tracked+=($(process_tree "$pgid" $(pgrep -g "$pgid" || true) | sort -u))
  done
  for pgid in "${groups[@]}"; do signal_group TERM "$pgid"; done
  for pid in "${tracked[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 50); do
    local running=0
    for pgid in "${groups[@]}"; do group_alive "$pgid" && running=1; done
    for pid in "${tracked[@]}"; do alive "$pid" && running=1; done
    [ "$running" -eq 0 ] && break
    sleep 0.1
  done
  for pgid in "${groups[@]}"; do signal_group KILL "$pgid"; done
  for pid in "${tracked[@]}"; do kill -KILL "$pid" 2>/dev/null || true; done
}

on_exit() {
  local status=$?
  trap - EXIT INT TERM
  stop_all
  local pid port leaked=0
  sleep 0.2  # let KILLed processes be reaped before checking
  for pid in "${tracked[@]}"; do
    if alive "$pid"; then echo "e2e: process $pid survived cleanup" >&2; leaked=1; fi
  done
  for port in "$API_PORT" "$WEB_PORT"; do
    if port_in_use "$port"; then echo "e2e: port $port is still in use after cleanup" >&2; leaked=1; fi
  done
  [ "$status" -eq 0 ] && [ "$leaked" -ne 0 ] && status=1
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_group() {  # log_file, command...: start in a new session; its pid is the process-group id
  local log="$1"; shift
  setsid "$@" > "$log" 2>&1 &
  groups+=("$!")
}

wait_for() {  # url, label
  local pgid="${groups[-1]}"
  for _ in $(seq 1 120); do
    if ! group_alive "$pgid"; then echo "$2 exited early; see $ARTIFACTS" >&2; return 1; fi
    curl -fsS -o /dev/null "$1" 2>/dev/null && return 0
    sleep 0.5
  done
  echo "$2 did not become ready" >&2
  return 1
}

for port in "$API_PORT" "$WEB_PORT"; do
  if port_in_use "$port"; then echo "e2e: port $port is already in use; refusing to start" >&2; exit 2; fi
done

cd "$ROOT/backend"
"$PYTHON" -m scripts.seed_e2e_fixtures --check-only
"$PYTHON" -m alembic upgrade head
"$PYTHON" -m scripts.seed_demo
"$PYTHON" -m scripts.seed_e2e_fixtures

start_group "$ARTIFACTS/api.log" "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
wait_for "http://127.0.0.1:$API_PORT/health" "API"

cd "$ROOT/frontend"
start_group "$ARTIFACTS/vite.log" env OH_API_TARGET="http://127.0.0.1:$API_PORT" npx vite --port "$WEB_PORT" --strictPort
wait_for "http://localhost:$WEB_PORT/" "Vite"

# Playwright runs in its own process group too, in the background, so that a signal interrupts `wait`
# at once (bash defers traps until a foreground command finishes) and cleanup stops it and its browser.
OH_BASE_URL="http://localhost:$WEB_PORT" OH_API_URL="http://127.0.0.1:$API_PORT" setsid npx playwright test "$@" &
groups+=("$!")
wait "$!"
