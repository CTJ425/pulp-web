# Lab Local Mirror 排錯手冊 (TROUBLESHOOTING)

適用範圍:Pulp 3(pulpcore + pulp_rpm / pulp_deb / pulp_container)、BFF、Nginx、用戶端。
建議搭配 `VERIFICATION.md` 的檢查步驟一起使用。

---

## 0. 排錯總原則(先做這三件事)

1. **確認服務健康**:
   ```bash
   curl -s https://mirror.lab.local/pulp/api/v3/status/ | jq
   ```
   確認 `database_connection.connected: true`、`redis_connection.connected: true`、
   `online_workers` 至少 1 個、`online_content_apps` 至少 1 個。

2. **找出對應的 task**:Pulp 幾乎所有失敗都會落在 task 裡。
   ```bash
   pulp task list --state failed --limit 5
   # 或
   curl -su admin:PASS "https://mirror.lab.local/pulp/api/v3/tasks/?state=failed&ordering=-pulp_created&limit=5" | jq '.results[] | {name, error}'
   ```
   `error.description` 與 `error.traceback` 是最重要的線索。

3. **看服務日誌**:
   ```bash
   docker compose logs -f pulp          # single-container
   journalctl -u pulpcore-worker@1 -f   # 套件安裝方式
   docker compose logs -f nginx bff
   ```

---

## 1. 服務層問題

### 1.1 API 回 502 / 連不上

| 檢查 | 指令 |
|------|------|
| 容器狀態 | `docker compose ps`(全部應為 healthy/running) |
| pulp-api 是否起來 | `docker compose logs pulp \| grep -i "listening\|error"` |
| Nginx upstream 設定 | `nginx -t`;確認 proxy_pass 指到正確 port |
| Port 衝突 | `ss -ltnp \| grep -E '80\|443\|24817\|24816'` |

常見原因:PostgreSQL 尚未 ready 就啟動 pulp(重啟順序問題)→ 設 compose `depends_on` + healthcheck。

### 1.2 `online_workers` 為空 / task 一直卡在 waiting

- worker 掛掉或連不上 Redis/PostgreSQL:
  ```bash
  docker compose logs pulp | grep -i worker
  ```
- Task 佇列塞滿:查 running 中是否有巨型 sync 佔住所有 worker;增加 worker 數:
  `PULP_WORKERS=4`(或 compose 中多開 worker service)。
- 曾經 kill -9 導致殘留 task:
  ```bash
  pulp task list --state running   # 確認是否殭屍
  pulp task cancel --href <task_href>
  ```

### 1.3 資料庫 migration 錯誤(升級後)

```bash
docker compose exec pulp pulpcore-manager migrate --check
docker compose exec pulp pulpcore-manager migrate
```
升級前務必備份 DB;plugin 與 pulpcore 版本相依表要對齊(不要單獨升 plugin)。

---

## 2. 同步 (Sync) 問題 — 通用

### 2.1 同步失敗:先看 error.description

```bash
curl -su admin:PASS "$TASK_HREF" | jq '{state, error}'
```

| 錯誤訊息片段 | 原因 | 處理 |
|--------------|------|------|
| `407` / `ProxyError` | 對外需經 proxy | remote 設 `proxy_url`(含帳密用 `proxy_username/password`) |
| `SSLCertVerificationError` | 上游憑證或中間人 proxy | 檢查 `ca_cert`;必要時 remote 設 `tls_validation=false`(僅限測試) |
| `401` / `403` | 上游需認證 | remote 設 `username/password`(Docker Hub、RHEL CDN 等) |
| `404` on repomd.xml / Release | remote URL 打錯 | URL 需指到含 `repodata/` 的層級(RPM)或 dist 根(DEB),見 §3/§4 |
| `TimeoutError` / `ClientConnectorError` | 網路不通、DNS | 從 mirror server 上 `curl -v` 同一 URL 驗證 |
| `DigestValidationError` | 上游檔案在同步中被更新、或上游壞檔 | 重跑 sync;持續發生則換上游 mirror |
| `Response payload is not completed` | 連線被中斷(上游或 proxy) | 調低 remote `download_concurrency`(如 5),重試 |

### 2.2 同步很慢

- 降低單一 remote `download_concurrency` 反而可避免被上游限流;多 repo 並行則增 worker。
- 首次同步大 repo 屬正常(Ubuntu universe 數小時起跳);改用 `on_demand` 策略立即可用。
- 檢查 mirror server 對外頻寬是否被其他流量吃滿。

### 2.3 同步成功但用戶端看不到新內容

Pulp 的內容流是 **sync → (publication) → distribution**。三種型態行為不同:

- **RPM / DEB**:sync 後需有 Publication 且 distribution 指向它。若 repo 設定 `autopublish=true`
  則自動處理;否則手動:
  ```bash
  pulp rpm publication create --repository my-repo
  pulp rpm distribution update --name my-dist --repository my-repo   # 或 --publication
  ```
- **Container**:無 publication 概念,distribution 直接指 repository,sync 完即生效。
- Distribution 被凍結(pin 在舊 version)也會造成「看不到新內容」— 檢查 UI 的凍結狀態。

---

## 3. RPM 專屬問題

### 3.1 remote URL 正確層級

URL 必須是「其下有 `repodata/repomd.xml`」的目錄,例如:
```
https://download.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/
```
驗證:`curl -sI <URL>/repodata/repomd.xml` 應回 200。

### 3.2 dnf 端 `repomd.xml missing` / metadata 過期

```bash
dnf clean all && dnf --disablerepo='*' --enablerepo='lab-*' makecache
```
若仍失敗:確認 distribution base_path 與 `.repo` 檔 baseurl 一致;
瀏覽器直接開 `https://mirror.lab.local/pulp/content/<base_path>/repodata/repomd.xml`。

### 3.3 GPG 檢查失敗

- Mirror 不會重簽套件,gpgkey 應仍指向對應發行版的 key(可放到 mirror 上的 `/keys/` 提供下載)。
- `gpgcheck=1` 驗的是 RPM 套件簽章;`repo_gpgcheck` 驗的是 repodata 簽章 —
  Pulp 產生的 metadata 預設未簽,**用戶端 `repo_gpgcheck` 必須為 0**,除非你在 Pulp 上設定 signing service。

### 3.4 `Checksum type sha1 is not allowed` / 舊 EL7 repo 同步失敗

老 repo 使用 SHA-1。在 Pulp settings 放寬:
```python
ALLOWED_CONTENT_CHECKSUMS = ["sha1", "sha224", "sha256", "sha384", "sha512"]
```
改完需執行:
```bash
pulpcore-manager handle-artifact-checksums
```
並重啟服務。(安全性:僅在確實需要鏡像舊發行版時開啟。)

### 3.5 只想同步部分套件

pulp_rpm 支援以 `includes`/`excludes`(依套件名 glob)做過濾同步,或使用
`sync --skip-type srpm` 跳過 source RPM 節省空間。

---

## 4. DEB 專屬問題

### 4.1 remote 設定重點

pulp_deb 的 remote 需要三個關鍵欄位:
```
url:            http://archive.ubuntu.com/ubuntu/     (dist 樹的根,不含 dists/)
distributions:  "noble noble-updates noble-security"
components:     "main universe"        (可省略=全部)
architectures:  "amd64"                (可省略=全部,強烈建議指定以省空間)
```
常見錯誤:把 `url` 設到 `.../dists/noble/` → 404。

### 4.2 apt 端 `Release file is not valid yet / expired`

- mirror server 或用戶端時間不同步 → 校時 (chrony/ntp)。
- 同步太久沒跑,上游 Release 已換 → 重新 sync。

### 4.3 `NO_PUBKEY` / 簽章驗證失敗

- 預設 pulp_deb publication 會沿用上游簽章結構(verbatim publisher)或產生未簽的 Release。
- 兩種解法:
  1. 使用 **verbatim publication**,完整保留上游簽章,用戶端沿用原 keyring — 最省事。
     verbatim 是獨立 API endpoint,pulp-cli 支援與否依版本而定,直接打 API 最穩:
     ```bash
     curl -su admin:PASS -X POST \
       https://mirror.lab.local/pulp/api/v3/publications/deb/verbatim/ \
       -H 'Content-Type: application/json' -d '{"repository": "<REPO_HREF>"}'
     ```
  2. 一般 publication + 在 Pulp 設 signing service 用自家 key 簽,用戶端匯入該 key。
- 臨時繞過(僅測試):sources.list 加 `[trusted=yes]`。

### 4.4 apt update 出現 `Skipping acquire of configured file ... doesn't have component`

sources.list 要求的 component/architecture 未包含在 remote 同步範圍 → 調整 remote 的
`components` / `architectures` 後重新 sync + publish。

---

## 5. Container 專屬問題

### 5.1 Docker Hub rate limit(`toomanyrequests`)

- 在 container remote 設定 Docker Hub 帳密(付費帳號更佳)。
- 改用 pull-through cache distribution,命中快取即不打上游。
- 錯誤確認:task error 中出現 `429` 或 `toomanyrequests: You have reached your pull rate limit`。

### 5.2 remote 設定重點

```
url:           https://registry-1.docker.io      (不是 hub.docker.com)
upstream_name: library/nginx                     (官方 image 要加 library/)
include_tags:  ["1.27*", "latest"]               (強烈建議,否則全 tag 同步會非常大)
```

### 5.3 `docker pull` 失敗:`http: server gave HTTP response to HTTPS client`

registry 必須走 TLS,或在用戶端 daemon.json 加 `insecure-registries`(不建議)。
正解:Nginx 上好憑證,用戶端信任內部 CA:
```bash
sudo cp lab-ca.crt /etc/docker/certs.d/mirror.lab.local/ca.crt   # docker
sudo cp lab-ca.crt /usr/local/share/ca-certificates/ && update-ca-certificates
```

### 5.4 `manifest unknown` / `name unknown`

- distribution base_path 與 pull 路徑不一致:pull 路徑 = `mirror.lab.local/<base_path>:<tag>`。
- 該 tag 不在 `include_tags` 範圍 → 調整 remote 後重 sync。
- 用 registry API 直接驗證(見 VERIFICATION §4.2)。

### 5.5 大 image push/pull 中斷、`blob upload unknown`

Nginx 需要:
```nginx
client_max_body_size 0;
proxy_request_buffering off;
proxy_buffering off;
proxy_read_timeout 900s;
chunked_transfer_encoding on;
```
並確認 `/v2/` location 正確轉發到 pulp-content(若部署啟用 token auth,`/token` 端點也要通;
本專案預設 `TOKEN_AUTH_DISABLED = True`,見 DEPLOYMENT §1.2)。

### 5.6 pull 到舊版 image

Container distribution 直接反映 repository 最新內容;若 pin 過 version 或 tag 未更新,
確認 sync task 成功且 `include_tags` 涵蓋該 tag,再 `docker pull` 時加 `--disable-content-trust`
無效於此,應以 digest 驗證(VERIFICATION §4.3)。

---

## 6. 前端 / BFF / Nginx 問題

| 症狀 | 檢查 |
|------|------|
| UI 登入後所有列表空白 | 瀏覽器 devtools 看 `/api/v1/*` 是否 401/500;BFF 日誌;BFF 到 Pulp 的服務帳號是否過期 |
| UI 觸發 sync 沒反應 | BFF 是否有把 Pulp 回的 task href 回傳;CORS 設定(BFF 需允許前端 origin) |
| task 進度不更新 | 前端輪詢間隔;BFF 對 `tasks/{id}` 的代理是否 cache 住(Nginx `proxy_cache off`) |
| 大檔下載 502/timeout | pulp-content 的 proxy timeout 拉長;on_demand 首抓會較慢屬正常 |
| Mixed content / CORS | 全站統一 HTTPS;BFF 回應加正確 `Access-Control-Allow-Origin` |

---

## 7. 磁碟與內容治理

### 7.1 磁碟用量偏高

```bash
df -h /var/lib/pulp
du -sh /var/lib/pulp/media
```
處置順序:
1. 降低各 repo `retain_repo_versions`(例如 3)。
2. 刪除不需要的 repository versions / repositories。
3. **執行 orphan cleanup**(刪掉沒有任何 repo version 引用的內容):
   ```bash
   pulp orphan cleanup --protection-time 1440   # 保護 24h 內新內容
   ```
4. RPM 大宗來源:srpm 與多餘架構 → 用 sync filter 排除。

### 7.2 Orphan cleanup 跑了但空間沒少

- `protection-time` 內的內容不會刪。
- 內容仍被某個舊 repository version 引用 → 先刪 version。
- on_demand 的 artifact 本來就不大;佔空間的是 immediate 同步內容。

---

## 8. 快速診斷指令備忘 (Cheat Sheet)

```bash
# 服務健康
curl -s https://mirror.lab.local/pulp/api/v3/status/ | jq '.online_workers, .online_content_apps'

# 最近失敗任務
pulp task list --state failed --limit 5

# 某 repo 的最新版本內容摘要
pulp rpm repository version show --repository my-repo

# 從 mirror server 手動測上游連通
curl -vI --proxy $HTTP_PROXY https://download.rockylinux.org/.../repomd.xml

# 用戶端 dnf 詳細除錯
dnf -v --disablerepo='*' --enablerepo='lab-*' makecache

# 用戶端 apt 詳細除錯
apt -o Debug::Acquire::http=true update 2>&1 | head -50

# registry v2 連通
curl -sI https://mirror.lab.local/v2/ ; echo
curl -s https://mirror.lab.local/v2/<base_path>/tags/list | jq
```

---

## 9. 升級與備份注意事項

- 升級順序:備份 DB → 停 worker → 升級 image(pulpcore 與 plugins 版本相容表)→ migrate → 起服務 → 跑 VERIFICATION.md 冒煙測試。
- 備份最小集合:PostgreSQL dump + `/var/lib/pulp/media` + settings.py + compose.yml。
- 還原後務必重跑一次三種型態的端到端驗證。
