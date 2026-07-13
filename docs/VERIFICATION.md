# Lab Local Mirror 驗證手冊 (VERIFICATION)

目的:提供**部署後驗收**與**日常冒煙測試**的標準步驟。
每個 Phase 上線、每次升級後,都應完整跑過本文件;§2–§4 亦可作為 CI 定期健檢腳本的依據。

慣例:
- Mirror 網址以 `https://mirror.lab.local` 為例。
- `admin:PASS` 代表 Pulp 服務帳號;實務上請放環境變數,勿寫死。
- ✅ = 通過條件。

---

## 1. 部署與平台層驗證(部署後第一步)

依部署階段擇一執行 §1A(Docker Compose)或 §1B(Kubernetes),之後**兩者都必須**通過 §1C 共通平台驗證。

---

### 1A. Docker Compose 部署驗證(Stage 1)

#### 1A.1 容器狀態

```bash
docker compose ps --format 'table {{.Name}}\t{{.State}}\t{{.Status}}'
```
✅ `postgres`、`redis`、`pulp`、`bff`、`frontend`、`nginx` 全部 `running`,有 healthcheck 者為 `healthy`
(P0 階段 bff/frontend 尚未實作,允許缺席;P1 起必須齊備)
✅ `docker compose ps -a | grep -i restart` 無反覆重啟(RestartCount 不增加)

#### 1A.2 容器日誌無致命錯誤

```bash
docker compose logs --since 10m pulp  | grep -iE 'error|traceback' | grep -v 'errors=0' || echo CLEAN
docker compose logs --since 10m bff nginx | grep -iE ' 5[0-9][0-9] |error' || echo CLEAN
```
✅ 無持續性 ERROR / traceback(啟動期一次性警告可接受,需註記)

#### 1A.3 Volume 與權限

```bash
docker compose exec pulp bash -c 'touch /var/lib/pulp/.write_test && rm /var/lib/pulp/.write_test && echo WRITABLE'
df -h /srv/pulp
```
✅ pulp 容器可寫 storage;`/srv/pulp` 掛載在預期的大容量磁碟上(非 root 系統碟)

#### 1A.4 重啟存活測試

```bash
docker compose restart && sleep 30
curl -sf https://mirror.lab.local/pulp/api/v3/status/ >/dev/null && echo OK
```
✅ 全部服務自動恢復,API 於 60 秒內可用;既有 repo 資料仍在(`pulp rpm repository list` 非空)

---

### 1B. Kubernetes 部署驗證(Stage 2)

#### 1B.1 Operator 與 CR 狀態

```bash
kubectl -n pulp-mirror get deploy pulp-operator-controller-manager
kubectl -n pulp-mirror get pulp mirror -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'
```
✅ operator Deployment Ready
✅ Pulp CR 的 conditions 全為 `True`(如 `Pulp-Operator-Finished-Execution=True`,實際名稱依版本)

#### 1B.2 Pods / Replicas

```bash
kubectl -n pulp-mirror get pods -o wide
```
✅ `*-api-*` ×2、`*-content-*` ×2、`*-worker-*` >=2、`bff` ×2、`frontend` ×2 全部 `Running` 且 `READY x/x`
✅ 無 `CrashLoopBackOff` / `ImagePullBackOff`;`kubectl get events -n pulp-mirror --sort-by=.lastTimestamp | tail -20` 無反覆 Warning
✅ pods 分散於不同節點(api/content 各自不同節點,驗 anti-affinity 或至少非全擠一台)

#### 1B.3 儲存

```bash
kubectl -n pulp-mirror get pvc
# RWX 方案:
kubectl -n pulp-mirror exec deploy/<content-deploy> -- sh -c 'touch /var/lib/pulp/.wt && rm /var/lib/pulp/.wt && echo WRITABLE'
```
✅ PVC 全部 `Bound`,storage PVC accessMode 為 `RWX`(檔案後端方案)
✅ api / content / worker 均能讀寫同一 storage(RWX)— 或 S3 方案:上傳測試物件成功
✅ PostgreSQL PVC 位於預期 StorageClass

#### 1B.4 Service / Ingress / TLS

```bash
kubectl -n pulp-mirror get svc,ingress
curl -sI https://mirror.lab.local/ | head -1
curl -s  https://mirror.lab.local/pulp/api/v3/status/ | jq '.online_workers | length'
curl -sI https://mirror.lab.local/v2/ | head -1
```
✅ Ingress 取得位址;cert-manager 簽出的憑證有效(`kubectl -n pulp-mirror get certificate` Ready)
✅ `/`、`/api`、`/pulp`、`/v2` 四條路由皆可達(200/401 視端點)
✅ Ingress annotations 生效:`kubectl -n pulp-mirror describe ingress mirror | grep -E 'body-size|buffering|read-timeout'`

#### 1B.5 韌性(K8s 專屬)

```bash
# 殺一個 content pod,期間持續下載
kubectl -n pulp-mirror delete pod -l app.kubernetes.io/component=content --wait=false &
curl -sf -o /dev/null https://mirror.lab.local/pulp/content/rocky9-baseos/repodata/repomd.xml && echo SURVIVED
```
✅ 單一 api/content pod 被刪除時服務不中斷(replicas>=2 的意義)
✅ 節點 drain 演練:`kubectl drain <node> --ignore-daemonsets` 後所有 pod 重新排程成功並恢復 Ready
✅ worker pod 重啟後,重跑 sync 成功、無殘留鎖

#### 1B.6 CronJob 排程

```bash
kubectl -n pulp-mirror get cronjob
kubectl -n pulp-mirror create job --from=cronjob/sync-rocky9-baseos manual-sync-test
kubectl -n pulp-mirror logs job/manual-sync-test
```
✅ 手動觸發的 Job 成功,對應 Pulp task `completed`
✅ `concurrencyPolicy: Forbid` 生效(同 repo 同時觸發第二次會被跳過)

#### 1B.7 遷移後資料完整性(僅遷移場景)

✅ repo 數量與 Compose 環境一致(`pulp rpm/deb/container repository list` 比對)
✅ 任選各型態一個 repo,用戶端安裝/pull 成功(§2–§4 重跑)
✅ 舊 repository versions 仍可查詢、凍結功能正常

---

### 1C. 共通平台驗證

#### 1C.1 服務健康

```bash
curl -s https://mirror.lab.local/pulp/api/v3/status/ | jq
```
✅ `database_connection.connected == true`
✅ `redis_connection.connected == true`
✅ `online_workers` 陣列長度 >= 1(K8s:應等於 CR 宣告的 worker replicas)
✅ `online_content_apps` 陣列長度 >= 1(K8s:應等於 content replicas)
✅ `versions[]` 中包含 `core`、`rpm`、`deb`、`container` 四個 component

#### 1C.2 TLS 與憑證

```bash
echo | openssl s_client -connect mirror.lab.local:443 2>/dev/null | openssl x509 -noout -dates -subject
```
✅ 憑證未過期、SAN 包含 `mirror.lab.local`
✅ 用戶端主機已信任內部 CA(`curl https://mirror.lab.local/ -sI` 不需 `-k`)

#### 1C.3 Web UI / BFF

```bash
curl -sI https://mirror.lab.local/            # 前端
curl -s  https://mirror.lab.local/api/v1/health | jq   # BFF
```
✅ 前端回 200;BFF health 回 `{"status":"ok"}` 且能列出 repos(登入後)

---

## 2. RPM 端到端驗證

以 Rocky 9 BaseOS 為例。

### 2.1 建立與同步(CLI 版,UI 亦可)

```bash
pulp rpm remote create --name rocky9-baseos \
  --url https://download.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/ \
  --policy on_demand

pulp rpm repository create --name rocky9-baseos --remote rocky9-baseos --autopublish
pulp rpm repository sync --name rocky9-baseos          # 會等待 task 完成
pulp rpm distribution create --name rocky9-baseos \
  --base-path rocky9-baseos --repository rocky9-baseos
```
✅ sync task `state == completed`
✅ `pulp rpm repository version show --repository rocky9-baseos` 顯示套件數 > 0

### 2.2 Metadata 可取得

```bash
curl -sI https://mirror.lab.local/pulp/content/rocky9-baseos/repodata/repomd.xml
```
✅ HTTP 200,`Content-Type` 為 xml

### 2.3 用戶端實測(在一台測試 VM)

```bash
sudo tee /etc/yum.repos.d/lab-test.repo <<'EOF'
[lab-rocky9-baseos]
name=Lab Mirror Test
baseurl=https://mirror.lab.local/pulp/content/rocky9-baseos/
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-9
EOF

sudo dnf clean all
sudo dnf --disablerepo='*' --enablerepo='lab-rocky9-baseos' makecache
sudo dnf --disablerepo='*' --enablerepo='lab-rocky9-baseos' install -y zsh
```
✅ makecache 成功;安裝成功且 GPG 驗證通過
✅ `dnf repoquery --qf '%{repoid}' zsh` 顯示來源為 `lab-rocky9-baseos`

### 2.4 流量驗證(確認真的沒往外抓)

在測試 VM 上:
```bash
sudo tcpdump -ni any 'port 443 and not host <mirror-ip>' &
sudo dnf reinstall -y zsh
```
✅ 安裝期間 tcpdump 無對外部 IP 的流量(僅對 mirror)

### 2.5 on_demand 快取行為

第一次抓某套件後,在 mirror server(`/var/lib/pulp` 是容器內路徑,host 上是 `/srv/pulp/storage`):
```bash
docker compose exec pulp find /var/lib/pulp/media -newermt '-10 minutes' -type f | head
```
✅ 出現新 artifact,代表首抓已快取;第二台 VM 安裝同套件時 mirror 不再向上游請求
(可在 mirror server 對外介面 tcpdump 驗證)。

---

## 3. DEB 端到端驗證

以 Ubuntu 24.04 (noble) main 為例。

### 3.1 建立與同步

```bash
pulp deb remote create --name ubuntu-noble \
  --url http://archive.ubuntu.com/ubuntu/ \
  --distribution noble --component main --architecture amd64 \
  --policy on_demand

pulp deb repository create --name ubuntu-noble --remote ubuntu-noble
pulp deb repository sync --name ubuntu-noble
pulp deb publication create --repository ubuntu-noble    # 或 verbatim
pulp deb distribution create --name ubuntu-noble \
  --base-path ubuntu-noble --repository ubuntu-noble
```
✅ sync 與 publication task 均 `completed`

### 3.2 Metadata 可取得

```bash
curl -sI https://mirror.lab.local/pulp/content/ubuntu-noble/dists/noble/Release
```
✅ HTTP 200

### 3.3 用戶端實測

```bash
echo "deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://mirror.lab.local/pulp/content/ubuntu-noble/ noble main" | \
  sudo tee /etc/apt/sources.list.d/lab-test.list
# 若採非 verbatim publication 且未設 signing service,測試時改用 [trusted=yes]

sudo apt update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/lab-test.list \
                -o Dir::Etc::sourceparts=/dev/null
sudo apt install -y htop
```
✅ `apt update` 無簽章錯誤(依採用的簽章策略)
✅ `apt-cache policy htop` 顯示來源為 `mirror.lab.local`

### 3.4 一致性抽查

```bash
# 比對 mirror 與上游同一 .deb 的 SHA256
curl -s https://mirror.lab.local/pulp/content/ubuntu-noble/pool/main/h/htop/<file>.deb | sha256sum
curl -s http://archive.ubuntu.com/ubuntu/pool/main/h/htop/<file>.deb | sha256sum
```
✅ 兩者一致

---

## 4. Container 端到端驗證

### 4.1 建立與同步(以 nginx 為例)

```bash
pulp container remote create --name dockerhub-nginx \
  --url https://registry-1.docker.io \
  --upstream-name library/nginx \
  --include-tags '["1.27","latest"]'

pulp container repository create --name nginx --remote dockerhub-nginx
pulp container repository sync --name nginx
pulp container distribution create --name nginx \
  --base-path library/nginx --repository nginx
```
✅ sync task `completed`

### 4.2 Registry API 驗證

```bash
curl -sI https://mirror.lab.local/v2/                       # ✅ 200(token auth 已停用,匿名可讀)
curl -s  https://mirror.lab.local/v2/library/nginx/tags/list | jq
```
✅ tags/list 包含 `1.27`、`latest`
(若部署改為啟用 token auth,此處會回 401,需先向 `/token?scope=repository:<path>:pull` 換匿名 token 再帶 Bearer)

### 4.3 用戶端 pull 與 digest 驗證

```bash
docker pull mirror.lab.local/library/nginx:1.27
docker inspect --format '{{index .RepoDigests 0}}' mirror.lab.local/library/nginx:1.27
# 與上游 digest 比對(可在有外網的機器上)
docker pull nginx:1.27 && docker inspect --format '{{index .RepoDigests 0}}' nginx:1.27
```
✅ pull 成功、兩邊 sha256 digest 相同
✅ 容器可正常啟動:`docker run --rm mirror.lab.local/library/nginx:1.27 nginx -v`

### 4.4 registry-mirror 透明模式(若採方式 A)

在設定了 `registry-mirrors` 的主機:
```bash
docker system prune -af   # 清本地快取(測試機)
docker pull nginx:1.27
```
✅ pull 成功;同時在 mirror server 的 pulp-content / nginx access log 看到對應請求
✅ 拔掉測試機對外網路(或防火牆擋外)後仍可 pull 已快取的 image

### 4.5 Rate limit 防護驗證

```bash
# 連續 pull 已快取 image 多次
for i in $(seq 1 5); do docker pull mirror.lab.local/library/nginx:latest; done
```
✅ mirror server 對 registry-1.docker.io 無新增請求(對外 tcpdump 或上游帳號用量頁確認)

---

## 5. 版本凍結 / 回滾驗證 (US-04)

```bash
# 1. 記下目前版本
pulp rpm repository version list --repository rocky9-baseos

# 2. 上游更新後 sync 產生新 version,確認 latest 有新套件
# 3. 凍結:把 distribution 指回舊 version 的 publication
pulp rpm publication create --repository rocky9-baseos --version <N-1>
# ⚠️ distribution 的 repository 與 publication 互斥:
#    建立時若綁了 --repository,必須同時清空才能改指 publication
pulp rpm distribution update --name rocky9-baseos \
  --repository "" --publication <PUB_HREF_OF_N-1>

# 解除凍結(指回 latest):
pulp rpm distribution update --name rocky9-baseos \
  --publication "" --repository rocky9-baseos
```
> 若 CLI 版本不接受空字串清欄位,改直接 PATCH API:
> `{"repository": null, "publication": "<href>"}`。
✅ 用戶端 `dnf makecache` 後查到的套件版本回到舊版
✅ UI 上該 repo 顯示「pinned @ version N-1」
✅ 解除凍結(指回 latest)後,新套件再次可見

---

## 6. Web UI 功能驗收(對應 User Stories)

| 案例 | 步驟 | ✅ 條件 |
|------|------|--------|
| US-01 | 以 viewer 登入 → Repositories → 任一 repo → Client Setup | 顯示可複製的 .repo / sources.list / registry 設定,內容與實際 base_path 一致 |
| US-02 | 以 operator 登入 → 新增 Repo 精靈建立一個 deb repo → Sync now | task 出現在 Tasks 頁並最終 completed;repo 列表更新「上次同步時間」 |
| US-03 | 於 Tasks 頁觀察一個進行中 sync | 有進度顯示;人為填錯 URL 的 repo sync 後,失敗原因可在 UI 讀到 |
| US-04 | Repo 詳情 → 選舊版本 → Pin | 見 §5 |
| US-05 | Admin → Storage | 總用量與 `df -h` 相符(±5%);觸發 orphan cleanup 產生 task 並完成 |
| US-06 | 以 viewer 嘗試按 Sync | 被拒(403 或按鈕不可用);operator 可以 |

---

## 7. 韌性與維運演練

| 演練 | 步驟 | ✅ 條件 |
|------|------|--------|
| 上游斷線 | 防火牆擋 mirror 對外 → 用戶端安裝**已快取**套件 | 成功(on_demand 未快取項目失敗屬預期,錯誤訊息清楚) |
| worker 重啟 | sync 進行中 `docker compose restart` worker | task 最終 failed/canceled 有明確狀態,重跑 sync 成功,無 DB 殘留鎖 |
| 磁碟壓力 | 填充磁碟至告警閾值 | 監控發出告警;orphan cleanup 後空間回收 |
| 備份還原 | 依 TROUBLESHOOTING §9 還原到乾淨主機 | §1–§4 冒煙全過,RTO <= 4 小時 |

---

## 8. 冒煙測試腳本骨架(建議放 CI 每日跑)

實作於 `scripts/smoke.sh`(dev 環境以 `MIRROR_URL`/repo 名稱環境變數覆寫,打 fixtures 建的 tiny repo):

```bash
#!/usr/bin/env bash
set -euo pipefail
M=${MIRROR_URL:-https://mirror.lab.local}

fail() { echo "FAIL: $1"; exit 1; }

# 平台
curl -sf $M/pulp/api/v3/status/ | jq -e '.online_workers | length >= 1' >/dev/null || fail "no workers"

# RPM metadata
curl -sfI $M/pulp/content/rocky9-baseos/repodata/repomd.xml >/dev/null || fail "rpm metadata"

# DEB metadata
curl -sfI $M/pulp/content/ubuntu-noble/dists/noble/Release >/dev/null || fail "deb metadata"

# Container tags
curl -sf $M/v2/library/nginx/tags/list | jq -e '.tags | index("latest")' >/dev/null || fail "container tags"

# K8s 環境額外檢查(Stage 2;在具 kubeconfig 的 runner 上執行)
if command -v kubectl >/dev/null && kubectl -n pulp-mirror get pulp mirror >/dev/null 2>&1; then
  kubectl -n pulp-mirror get pods --no-headers | awk '$3!="Running" && $3!="Completed"' | grep -q . \
    && fail "pods not running"
  kubectl -n pulp-mirror get pvc --no-headers | awk '$2!="Bound"' | grep -q . \
    && fail "pvc not bound"
  kubectl -n pulp-mirror get certificate mirror-tls -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' \
    | grep -q True || fail "tls certificate not ready"
fi

echo "SMOKE OK $(date -Is)"
```
✅ 每日排程執行,失敗時發告警(mail / chat webhook)

---

## 9. 驗收簽核表

| 項目 | 章節 | 結果 | 簽核 | 日期 |
|------|------|------|------|------|
| Docker Compose 部署 (Stage 1) | §1A | ☐ | | |
| Kubernetes 部署 (Stage 2) | §1B | ☐ | | |
| 平台健康(共通) | §1C | ☐ | | |
| RPM E2E | §2 | ☐ | | |
| DEB E2E | §3 | ☐ | | |
| Container E2E | §4 | ☐ | | |
| 凍結/回滾 | §5 | ☐ | | |
| UI 驗收 | §6 | ☐ | | |
| 韌性演練 | §7 | ☐ | | |
| 冒煙自動化 | §8 | ☐ | | |
