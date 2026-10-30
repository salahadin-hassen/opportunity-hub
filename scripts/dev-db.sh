#!/usr/bin/env bash
# Isolated, user-owned PostgreSQL 16 cluster for local development and tests.
# Lives in .devdb/ (git-ignored), listens on localhost:5433, trust auth for the
# local "ohub" role only. Never touches the system cluster.
#
#   scripts/dev-db.sh init    create the cluster and the two databases (once)
#   scripts/dev-db.sh start   start it
#   scripts/dev-db.sh stop    stop it
#   scripts/dev-db.sh status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/.devdb/data"
PORT=5433
PG_BIN="${PG_BIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"

case "${1:-status}" in
  init)
    mkdir -p "$ROOT/.devdb"
    "$PG_BIN/initdb" -D "$DATA" -U ohub --auth=trust -E UTF8 >/dev/null
    "$0" start
    "$PG_BIN/createdb" -h localhost -p "$PORT" -U ohub opportunity_hub
    "$PG_BIN/createdb" -h localhost -p "$PORT" -U ohub opportunity_hub_test
    echo "Created opportunity_hub and opportunity_hub_test on localhost:$PORT"
    ;;
  start)
    "$PG_BIN/pg_ctl" -D "$DATA" -o "-p $PORT -k $ROOT/.devdb -c listen_addresses=localhost" -l "$ROOT/.devdb/log.txt" start
    ;;
  stop)
    "$PG_BIN/pg_ctl" -D "$DATA" stop
    ;;
  status)
    "$PG_BIN/pg_ctl" -D "$DATA" status
    ;;
  *)
    echo "usage: $0 init|start|stop|status" >&2
    exit 1
    ;;
esac
