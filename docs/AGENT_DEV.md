# AGENT_DEV.md — Claude Code 開發整合指南

目的:讓 Claude Code 在本專案能**自己開發、自己測試、自己排錯**,並界定安全邊界。
本文件給人看;給 agent 看的規則放在 repo 根目錄的 `CLAUDE.md`(每次 session 自動載入)。

> Claude Code 官方文件:https://docs.claude.com/en/docs/claude-code/overview
> 注意:hooks/settings 欄位隨版本演進,落地前以官方文件為準。

---

## 1. 兩種「連動」的定位

| 模式 | 說明 | 本專案採用 |
|------|------|-----------|
| 開發期(dev-time) | Claude Code 在 repo 內開發,透過 Bash 操作 compose/kubectl、跑測試,透過 **Playwright MCP** 操作瀏覽器測前端 | ✅ 主要模式 |
| 執行期(run-time) | 網頁本身的 AI 功能(如「AI 診斷失敗 task」按鈕),由 BFF 呼叫 **Anthropic API / Agent SDK** 實作 | Phase 2 選配,見 §7 |

Claude Code 是開發工具,不作為部署後系統的執行元件;正式服務內嵌 AI 一律走 API/SDK。

---

## 2. Agent 自我測試迴圈的基礎建設

Agent 能否自己測,取決於三件事:**可一鍵重建的環境、跑得快的測試、明確的成敗訊號(exit code)**。

### 2.1 Makefile 為唯一入口

所有操作收斂到 `make <target>`(清單見 CLAUDE.md),好處:
- Agent 不需要記/猜長指令,人與 agent 用同一套。
- 每個 target 保證「exit 0 = 成功」,agent 可以機械式判斷。
- CI 直接重用同一批 target,本機與 CI 行為一致。

### 2.2 迷你 fixtures:讓 sync 測試從小時變秒

`fixtures/` 內建三個極小上游,由 `make dev` 一併以靜態檔案服務(nginx)提供:

| Fixture | 內容 | 用途 |
|---------|------|------|
| `tiny-rpm/` | 2–3 個自製 rpm + `createrepo_c` 產生的 repodata | 測 rpm remote/sync/publish/distribution 全流程 |
| `tiny-deb/` | 2–3 個自製 deb + 手工 Release/Packages | 測 deb 全流程 |
| `tiny-registry/` | 一個幾 MB 的 image(如 busybox 重 tag)放本機 registry:2 | 測 container sync 與 pull-through |

規則(已寫入 CLAUDE.md):測試一律打 fixtures,不同步真實上游。
真實上游的驗證屬於 `VERIFICATION.md` 的人工/排程驗收,不進開發迴圈。

### 2.3 測試金字塔與對應驗收

| 層 | 工具 | 對應 |
|----|------|------|
| unit | pytest(BFF)、vitest(前端) | 純邏輯 |
| api | pytest + httpx,打 dev 環境的 BFF 與 Pulp | VERIFICATION §2–4 的 API 部分腳本化 |
| e2e | Playwright(CLI 跑測試)+ **Playwright MCP**(agent 互動式操作瀏覽器排錯) | VERIFICATION §6 UI 驗收腳本化 |
| smoke | `scripts/smoke.sh`(= VERIFICATION §8) | 部署後健檢 |

**把 VERIFICATION 的 ✅ 條件逐條轉成測試案例**是本專案文件維護的鐵律:
新增驗收條件 → 同 PR 內新增對應測試,文件註記測試檔路徑,例如:

```
✅ sync task completed            → tests/api/test_rpm_flow.py::test_sync_completes
✅ tags/list 包含 latest          → tests/api/test_container_flow.py::test_tags_list
✅ UI 觸發 sync 後 task 出現進度   → tests/e2e/sync.spec.ts
```

---

## 3. Claude Code 專案設定

### 3.1 檔案佈局

```
CLAUDE.md                     # 專案規則(已提供範本)
.claude/
  settings.json               # 權限與 hooks(進 git,團隊共用)
  agents/                     # 選配:自訂 subagent(如 pulp-debugger)
.mcp.json                     # 專案 MCP servers(進 git)
```

### 3.2 MCP servers(.mcp.json)

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--headless"]
    }
  }
}
```

- **Playwright MCP**:agent 可直接開瀏覽器操作 dev 前端(點按鈕、讀 console error、截圖),
  是「自己測 UI、自己排錯」的關鍵。E2E 迴歸仍以寫成 `.spec.ts` 為準,MCP 用於探索與除錯。
- K8s 需求以 Bash + `kubectl --kubeconfig .kube-dev/config` 即可,不必額外 MCP。

### 3.3 權限(.claude/settings.json 的 permissions)

原則:**開發所需全開、危險面明確 deny**。示意:

```json
{
  "permissions": {
    "allow": [
      "Bash(make *)",
      "Bash(docker compose *)",
      "Bash(kubectl --kubeconfig .kube-dev/config *)",
      "Bash(curl *)", "Bash(pytest *)", "Bash(npx playwright *)",
      "Read", "Edit"
    ],
    "deny": [
      "Read(~/.kube/**)",
      "Read(**/.env.prod)",
      "Bash(git push --force*)",
      "Bash(kubectl --context prod*)"
    ]
  }
}
```

### 3.4 Hooks:確定性的守門

CLAUDE.md 是「建議」,hooks 是「強制」——不管模型是否照做都會執行。建議三條:

| 事件 | 動作 | 目的 |
|------|------|------|
| PostToolUse(Edit/Write, `*.py`) | `ruff check --fix` + `ruff format` 該檔 | 每次編輯後自動 lint,agent 立即看到錯誤 |
| PostToolUse(Edit/Write, `*.ts`/`*.tsx`) | `eslint --fix` 該檔 | 同上 |
| PreToolUse(Bash) | 腳本檢查指令是否觸碰 prod(關鍵字 `mirror.lab.local` 之寫入方法、prod context),違規 **exit 2** 阻擋 | 護欄:防止 agent 排錯排到正式環境上 |

> Hook 阻擋要用 exit 2(exit 1 不會阻擋,是常見誤區)。設定細節見官方 hooks 文件。

### 3.5 Subagent(選配)

`.claude/agents/pulp-debugger.md`:專職排錯的 subagent,系統提示要點:
「輸入為失敗現象;依 `docs/TROUBLESHOOTING.md` §0 流程操作:status API → failed tasks → 容器 log,
對照 §2–5 錯誤表;輸出:根因、證據(指令與輸出摘錄)、建議修法。只讀不改。」
好處:把大量 log 探索隔離在 subagent 的 context,主對話只收結論。

---

## 4. 建議的 agent 工作流(給下 prompt 的人)

1. **一個任務一個分支、一個明確驗收**:
   「實作 US-02 新增 repo 精靈的 deb 分支;完成定義 = `make test-api` 中 `test_deb_flow` 全綠 + `make e2e` 的 `create-repo.spec.ts` 全綠。」
2. **要求先寫失敗測試再實作**(CLAUDE.md 已規範)。
3. 長任務用 plan mode 先審計畫,再放手執行。
4. 修 bug 給它現象與重現步驟即可,排錯路徑已寫進 CLAUDE.md/TROUBLESHOOTING,不必在 prompt 重複。

---

## 5. CI 整合(headless)

Claude Code 支援非互動執行(`claude -p`),適合 CI 內自動 review 或修測試:

```bash
# PR 自動安全審查(GitHub Actions 內)
gh pr diff "$PR" | claude -p --bare \
  --append-system-prompt "You are a security reviewer for this Pulp mirror project." \
  --allowedTools "Read" --output-format json > review.json
```

要點:
- CI 用 `--bare`:跳過本機 hooks/MCP/CLAUDE.md 自動載入,執行可重現;認證走 `ANTHROPIC_API_KEY`。
- 判斷成敗:branch on zero / non-zero exit code + 解析 `--output-format json`。
- 亦可直接採用官方 Claude Code GitHub Action。
- 不可逆操作(push、deploy)不交給 agent,由 pipeline 把關。

---

## 6. 文件維護規則(讓文件持續對 agent 友善)

1. **CLAUDE.md 保持小**(數百 token 級):只放規則、指令表、路徑指引;細節外移到 docs/ 並以路徑引用。
2. **TROUBLESHOOTING 用表格**維持「錯誤片段 → 原因 → 處置」三欄格式(agent 好比對);每次踩到新坑,同 PR 補一列。
3. **VERIFICATION 的 ✅ 必附測試路徑**(§2.3 鐵律);無法自動化的條目明確標 `[manual]`。
4. **Claude 犯過的錯寫回 CLAUDE.md**:發現 agent 重複犯某類錯(例如又想同步真實上游),就把禁令寫進 CLAUDE.md;需要保證的改用 hook。

---

## 7. Phase 2 選配:網頁內建 AI 診斷(run-time)

- 位置:BFF 新增 `POST /api/v1/tasks/{id}/diagnose`。
- 實作:BFF 以 Anthropic API(或 Agent SDK)送出:task 的 error.description/traceback + TROUBLESHOOTING 對照表(作為 context),回傳結構化診斷(根因/建議/相關文件章節)。
- 邊界:唯讀診斷,不自動執行修復;API key 存於 Secret;成本控制(僅 failed task 可觸發、加 rate limit)。
- 這與 Claude Code 無關,勿混用;Claude Code 僅存在於開發與 CI。
