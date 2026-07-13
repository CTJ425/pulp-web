#!/bin/sh
# 依環境變數產生 runtime 設定(SPEC §2.3.3:API base URL 以 runtime env 注入)
set -eu
cat > /usr/share/nginx/html/config.js <<EOF
window.__CONFIG__ = { apiBase: '${API_BASE_URL:-/api}' }
EOF
echo "runtime config: apiBase=${API_BASE_URL:-/api}"
