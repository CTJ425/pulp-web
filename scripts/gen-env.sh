#!/usr/bin/env bash
# 產生 deploy/compose/.env(不存在時);密碼隨機,不進 git(CLAUDE.md 秘密規則)
set -euo pipefail
ENV_FILE=${1:?usage: gen-env.sh <path-to-.env>}

[ -f "$ENV_FILE" ] && { echo "OK: $ENV_FILE 已存在,不覆寫"; exit 0; }

rand() { tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24; }

cat > "$ENV_FILE" <<EOF
# dev 環境自動產生($(date -Is));勿提交進 git
DB_PASSWORD=$(rand)
PULP_ADMIN_PASSWORD=$(rand)
HTTP_PORT=8080
CONTENT_ORIGIN=http://localhost:8080
EOF
chmod 600 "$ENV_FILE"
echo "OK: 已產生 $ENV_FILE"
