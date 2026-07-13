#!/usr/bin/env bash
# 在 tools 容器內執行(make seed):對 fixtures 建立 rpm/deb/container 三組
# remote + repository + (publication) + distribution,並完成 sync。可重複執行。
set -euo pipefail

P() {
  pulp --base-url "${PULP_BASE_URL:-http://pulp}" \
       --username "${PULP_USERNAME:-admin}" \
       --password "${PULP_PASSWORD:?PULP_PASSWORD required}" "$@"
}

exists() { P "$1" "$2" show --name "$3" >/dev/null 2>&1; }

echo "== RPM: tiny-rpm =="
exists rpm remote tiny-rpm || \
  P rpm remote create --name tiny-rpm --url http://fixtures/tiny-rpm/ --policy on_demand
exists rpm repository tiny-rpm || \
  P rpm repository create --name tiny-rpm --remote tiny-rpm --autopublish
P rpm repository sync --name tiny-rpm
exists rpm distribution tiny-rpm || \
  P rpm distribution create --name tiny-rpm --base-path tiny-rpm --repository tiny-rpm

echo "== DEB: tiny-deb =="
exists deb remote tiny-deb || \
  P deb remote create --name tiny-deb --url http://fixtures/tiny-deb/ \
    --distribution tiny --component main --architecture amd64 --policy on_demand
exists deb repository tiny-deb || \
  P deb repository create --name tiny-deb --remote tiny-deb
P deb repository sync --name tiny-deb
# 無 autopublish 的型態:最新 repo version 尚無 publication 才建(重跑 seed 不疊加)
ver=$(P deb repository show --name tiny-deb | jq -r '.latest_version_href')
if [ "$(P deb publication list --repository-version "$ver" | jq 'length')" = "0" ]; then
  P deb publication create --repository tiny-deb
fi
exists deb distribution tiny-deb || \
  P deb distribution create --name tiny-deb --base-path tiny-deb --repository tiny-deb

echo "== Container: tiny/hello =="
exists container remote tiny-hello || \
  P container remote create --name tiny-hello \
    --url http://upstream-registry:5000 --upstream-name tiny/hello
exists container repository tiny-hello || \
  P container repository create --name tiny-hello --remote tiny-hello
P container repository sync --name tiny-hello
exists container distribution tiny-hello || \
  P container distribution create --name tiny-hello --base-path tiny/hello --repository tiny-hello

echo "SEED OK"
