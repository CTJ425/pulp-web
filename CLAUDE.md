# CLAUDE.md — Lab Local Mirror 專案規則

> 本檔為 Claude Code 的專案記憶。保持精簡;細節放對應文件,用路徑指引。

## 專案是什麼

基於 Pulp 3 的 lab 套件鏡像服務(RPM / DEB / Container),含自建 BFF (FastAPI) 與前端 (React + TS)。
- 規格:`docs/SPEC.md`
- 部署:`docs/DEPLOYMENT.md`(Stage 1 = docker compose,Stage 2 = K8s + pulp-operator)
- 驗收條件:`docs/VERIFICATION.md`(✅ 條件逐步腳本化中,已腳本化者於文件內註記測試路徑,無法自動化者標 `[manual]`)
- 錯誤對照表:`docs/TROUBLESHOOTING.md`(排錯時**先查表再猜**)

## 目錄結構

```
bff/         FastAPI 專案(Python 3.12, uv 管理依賴)
frontend/    React + TypeScript (Vite)
deploy/
  compose/   Stage 1 compose.yml 與設定
  k8s/       Stage 2 manifests(Pulp CR、bff/frontend deploy、ingress、cronjobs)
tests/
  unit/      pytest 單元測試(不需環境)
  api/       pytest 打 BFF/Pulp API(需 dev 環境)
  e2e/       Playwright 前端測試(需 dev 環境)
scripts/     smoke.sh、seed-fixtures.sh 等
fixtures/    迷你上游(tiny-rpm / tiny-deb / tiny-registry),make dev 一併起服務
docs/        SPEC / DEPLOYMENT / VERIFICATION / TROUBLESHOOTING / AGENT_DEV
```

## 指令(一律透過 Makefile,勿自創指令)

| 指令 | 作用 | 成功條件 |
|------|------|---------|
| `make dev` | 啟動本機 dev 環境(compose + 迷你上游 fixtures) | exit 0,`make status` 全 healthy |
| `make status` | 檢查 dev 環境健康 | exit 0 |
| `make seed` | 建立測試用 repo(tiny-rpm / tiny-deb / tiny-image)並完成 sync | exit 0 |
| `make test` | 單元測試(快,無環境需求) | exit 0 |
| `make test-api` | API 整合測試 | exit 0 |
| `make e2e` | Playwright 前端測試 | exit 0 |
| `make smoke` | VERIFICATION §8 冒煙腳本 | exit 0 |
| `make lint` | ruff + oxlint + tsc -b | exit 0 |
| `make down` | 收掉 dev 環境 | — |

## 開發規則

- 改 code 後的最小驗證順序:`make lint` → `make test` → 涉及 API 則 `make test-api` → 涉及 UI 則 `make e2e`。
- 新功能必須附測試;修 bug 必須先寫重現該 bug 的失敗測試。
- BFF 對 Pulp 的非同步操作一律回 202 + task href;前端輪詢 task,不得阻塞等待。
- 秘密只從環境變數讀;禁止把任何密碼、token 寫進 code 或 compose 檔。
- 測試用的上游一律用 `fixtures/` 的迷你 repo,**不要**在測試中同步真實上游(Rocky/Ubuntu/Docker Hub)。

## 排錯規則(自己排錯時)

1. 任何失敗先跑 `make status`,再抓對應容器 log:`docker compose -f deploy/compose/compose.yml logs --since 5m <svc>`。
2. Pulp 相關錯誤:先查最近 failed task 的 `error.description`,對照 `docs/TROUBLESHOOTING.md` §2–§5 的表格。
3. 同一個修法嘗試兩次仍失敗 → 停止,總結目前發現與假設,回報而不是繼續亂試。

## 邊界(禁止事項)

- 禁止讀取或使用 `~/.kube/` 下任何 config;K8s 操作僅限 `deploy/k8s/kind-dev` 產生的 dev cluster(kubeconfig 於 `.kube-dev/config`)。
- 禁止對 `mirror.lab.local`(正式環境)做任何寫入操作;正式環境只讀不寫。
- 禁止 `git push --force`、禁止改動 `main` 分支;一律開 feature branch + PR。
- 禁止在測試中對外部真實服務(Docker Hub 等)發出大量請求。
