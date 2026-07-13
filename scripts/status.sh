#!/usr/bin/env bash
# dev 環境健康檢查(VERIFICATION §1A.1 的腳本化);全過 exit 0
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f deploy/compose/compose.yml --env-file deploy/compose/.env --profile dev"
HTTP_PORT=$(grep -E '^HTTP_PORT=' deploy/compose/.env | cut -d= -f2 || true)
HTTP_PORT=${HTTP_PORT:-8080}

fail=0
for s in postgres redis pulp nginx bff frontend fixtures upstream-registry; do
  cid=$($COMPOSE ps -q "$s" 2>/dev/null || true)
  if [ -z "$cid" ]; then
    echo "FAIL: $s 未建立(先跑 make dev)"
    fail=1
    continue
  fi
  state=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$cid")
  case "$state" in
    running|running/healthy) echo "OK:   $s ($state)" ;;
    *) echo "FAIL: $s ($state)"; fail=1 ;;
  esac
done

if curl -sf "http://localhost:${HTTP_PORT}/pulp/api/v3/status/" >/dev/null; then
  echo "OK:   pulp API via nginx (http://localhost:${HTTP_PORT}/pulp/api/v3/status/)"
else
  echo "FAIL: pulp API via nginx 不可達"
  fail=1
fi

exit "$fail"
