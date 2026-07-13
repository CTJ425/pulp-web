#!/usr/bin/env bash
# 冒煙測試(VERIFICATION §8 的實作)。在 tools 容器內以 make smoke 執行,
# 預設打 dev 環境的 fixtures repo;正式環境以環境變數覆寫:
#   MIRROR_URL=https://mirror.lab.local SMOKE_RPM_BASE=rocky9-baseos \
#   SMOKE_DEB_BASE=ubuntu-noble SMOKE_DEB_DIST=noble \
#   SMOKE_CTR_BASE=library/nginx SMOKE_CTR_TAG=latest scripts/smoke.sh
set -euo pipefail

M=${MIRROR_URL:-https://mirror.lab.local}
RPM_BASE=${SMOKE_RPM_BASE:-tiny-rpm}
DEB_BASE=${SMOKE_DEB_BASE:-tiny-deb}
DEB_DIST=${SMOKE_DEB_DIST:-tiny}
CTR_BASE=${SMOKE_CTR_BASE:-tiny/hello}
CTR_TAG=${SMOKE_CTR_TAG:-latest}

fail() { echo "FAIL: $1"; exit 1; }

# 平台健康(VERIFICATION §1C.1)
status=$(curl -sf "$M/pulp/api/v3/status/") || fail "status API 不可達"
echo "$status" | jq -e '.database_connection.connected'      >/dev/null || fail "database not connected"
echo "$status" | jq -e '.redis_connection.connected'         >/dev/null || fail "redis not connected"
echo "$status" | jq -e '.online_workers | length >= 1'       >/dev/null || fail "no online workers"
echo "$status" | jq -e '.online_content_apps | length >= 1'  >/dev/null || fail "no online content apps"
for c in core rpm deb container; do
  echo "$status" | jq -e --arg c "$c" '.versions[] | select(.component == $c)' >/dev/null \
    || fail "plugin $c 未安裝"
done

# RPM metadata(§2.2)
curl -sfI "$M/pulp/content/$RPM_BASE/repodata/repomd.xml" >/dev/null || fail "rpm metadata"

# DEB metadata(§3.2)
curl -sfI "$M/pulp/content/$DEB_BASE/dists/$DEB_DIST/Release" >/dev/null || fail "deb metadata"

# Container tags(§4.2)
curl -sf "$M/v2/$CTR_BASE/tags/list" | jq -e --arg t "$CTR_TAG" '.tags | index($t)' >/dev/null \
  || fail "container tags"

echo "SMOKE OK $(date -Is)"
