# 推廣前檢查：Atlas 0.4.1

檢查日期：2026-11-07。原始碼：`49ad21e727504c1cba1daaf3e1229b5a6a35ac43`。

結論：建議先修正以下 P1 問題，再向 X、Reddit、Hacker News 大規模推廣。目前基本安裝與指令探索可用，但 benchmark 尚不足以支持首頁的強烈宣稱，Confluence 內容保真與發布失敗行為也需要修正。

這次是審查；沒有修改產品程式、README 或 benchmark，也沒有推送、建立社群貼文或寫入 Atlassian。

## 已完成驗證

- 從公開 PyPI 在 `/tmp/atlas-launch-review` 的全新 tool/cache/bin 目錄安裝 `atlassian-atlas`，成功取得 0.4.1 與 5 個相依套件。
- 正式安裝版本的 `atlas --version`、主 help、Jira/Confluence help，以及所有 16 個子指令的 `--help` 均成功。
- 依 CONTRIBUTING 的方式執行三個測試腳本：16 + 5 + 5 = 26 個測試通過。`unittest discover` 找不到這些函式測試，不能把它的成功當作測試通過。
- GitHub 最新 Test 與 Release workflow 均成功，commit 與本機一致；v0.4.1 有 wheel 與 sdist。
- 已重現下列 benchmark、文件與內容處理問題；內容處理測試使用假資料／mock client，沒有修改遠端頁面。

## P1：推廣前應修正

### 1. Benchmark 接受失敗操作，無法據此驗證速度

位置：`benchmarks/benchmark_latency.py:98`、`:229`。

`time_cli` 不檢查 subprocess return code；`time_mcp` 不檢查 JSON-RPC error 或 `result.isError`。實測傳入退出碼 1 的 Python 程序，以及回傳 `isError: true` 的 mock gateway，兩者都產生正常的 timing sample。

腳本還硬編碼 `PROJ-123`、page `987923264`、搜尋條件，沒有驗證回應是否成功且語意相當。讀者直接執行可能是在測量不存在資源或認證錯誤的回應。

修正方向：失敗即停止並回傳非零退出碼；參數化 issue/page/JQL/CQL；驗證成功與資料對等；記錄每次原始 sample、版本、設定與有效結果數。這不證明歷史測量錯誤，但現有腳本無法排除此風險。

### 2. 「121x less context」不是目前證據所測量的量

位置：`README.md:5`、`:33`；`benchmarks/SCHEMA.md`。

108,867 / 901 = 120.83，算術正確。但分子是 73 個工具的完整 schema 集合，分母是只列 12 個操作的歷史 routing rule；文件本身說 schema 是按需載入，並承認多個 MCP 功能沒有 CLI 對等操作。不能把這個比值當成實際 context、完整功能替代或每次對話的節省比例。

文件中的 rule 為 900 字元（含尾端換行則 901），目前 `.cursor/rules` 的 Atlassian 區段為 1,492 字元；README 的新 routing snippet 又是另一份文字。應保留歷史版本與明確量測對象。

「20 turns 節省約 47,000 tokens」是估算模型，不是實測 session：缺少呼叫發生的 turn、實際 tokenizer、help 輸出、重複工具使用、context 壓縮與其他 MCP 是否仍啟用等條件。這是跨請求累計輸入量，也不等於單次 context window 的減少。

修正方向：首頁改以精簡輸出與 shell 整合的具體功能為主；把 schema 數字標為特定設定下的靜態描述文字比較。比較共同支援的工具，並納入 CLI help/discovery 的 context 成本。

### 3. 缺少 Mermaid renderer 時仍發布刪除圖表後的內容

位置：`atlas/commands/conf_publish.py:125`、`:148`、`:57`。

模擬 `mmdc` 不存在，輸入標題與 Mermaid 圖表，`run` 仍呼叫 Confluence PUT，body 只剩 `<h1>Diagram</h1>`。renderer 失敗也會刪除該區塊繼續。雖有 stderr 警告，操作仍以成功路徑結束，可能覆蓋原有完整頁面。

修正方向：預設在任何遠端寫入前停止；若要允許略過圖表，使用明確 opt-in。README 補上 Mermaid 的額外依賴，並在上傳前完成本地驗證。

### 4. Confluence 預設讀取輸出會破壞資料

位置：`atlas/commands/conf_get.py:82`。

重現案例：

- 表格 `Name | Value`、`Timeout | 30` 轉成 `NameValueTimeout30`。
- code macro 的 `x = "<tag>"` 轉成 `x = ""`，因為抽出 code 後又套用 HTML stripping。

這直接影響 coding agent 對技術文件的判讀，也表示「輸出更小」需要搭配內容完整性檢查，不能只比較字數。

修正方向：以結構化 HTML/storage parsing 保留 table/cell 邊界、code 與實體字元；補代表性 fixture。修正前，需完整內容的使用者可用 `atlas conf get <ID> --format storage`。

## P2：首次體驗與可信度問題

### 5. README 的免安裝指令必定失敗

位置：`README.md:66`。

實測 `uvx atlassian-atlas --help` exit 1：套件沒有名為 `atlassian-atlas` 的 executable。改成：

```bash
uvx --from atlassian-atlas atlas --help
```

`uv tool install atlassian-atlas` 已在乾淨環境驗證成功。source install 與 CONTRIBUTING 的 `uv pip install` 前還應加 `uv venv`，避免新 clone 沒有 virtualenv。PATH 指引宜提供 `uv tool update-shell`，不應假設單純重開 terminal 一定會解決 PATH。

### 6. 分頁結果會被當成完整結果

位置：`atlas/commands/conf_tree.py:18`、`jira_children.py:65`、`jira_search.py:37`。

Confluence tree 固定只取一頁 200 筆；mock 回傳 `_links.next` 時仍只呼叫一次。Jira children 在每層只取一頁，未接續 `nextPageToken`。Search 只取一頁本身可以是刻意限制，但當回應沒有 `total` 時，標題使用該頁長度，沒有表達可能還有資料。

修正方向：tree/children 正確分頁，或明確標註截斷；search 顯示 fetched count 與是否還有下一頁。AI 不應把缺漏樹狀結果當成完整專案結構。

### 7. 設定與寫入語意不一致

- `atlas/config.py:82`：只有三個 env var 都設定才採用 env。單獨以環境變數覆寫 token 會被忽略；已用假設定檔重現。應逐欄 merge，並驗證空值、JSON 格式與 URL。
- `conf create --body` 當成 storage XHTML，`conf update --body` 卻預設 Markdown。相同內容因 create/update 得到不同結果。統一語意或明確標示格式。
- 網路 timeout/connection failure 沒有集中處理，會顯示 Python traceback。建議短錯誤訊息、明確退出碼與可選 debug。

### 8. Benchmark 文件無法完整重現

- OUTPUT 明確說示範資料不是原始量測資料，因此目前不能重算 6,421 與 2,597 的原始總數。
- 缺少 schema 原始集合、逐次 timing、MCP server image/version、Docker/host/Python/Atlas 版本與原始配置。
- 9 處相對連結仍使用舊的 `BENCHMARKS-*.md` 路徑或錯誤的 `README.md` 相對位置。
- LATENCY 的指令 `python benchmark_latency.py` 未說明要先進入 `benchmarks`；從 repo root 應用 `python benchmarks/benchmark_latency.py`。
- latency 表格行加總為 CLI 2,083、MCP 26,652 ms，而總欄為 2,082、26,653；差異很小，可能是四捨五入，但應由原始資料生成並說明。
- ~416 ms 與 ~5,332 ms 是「五個操作各自中位數的平均」，不宜稱作所有 calls 的 pooled median。
- create/start/protocol/teardown 的時間拆分不是現有腳本直接測量的結果；尤其「protocol 固定 ~200 ms」與「long-lived 仍一定較慢」缺乏直接對照測量。

## 數字判定

| 宣稱 | 已核算 | 對外使用建議 |
|---|---|---|
| 121x context | 108,867 / 901 = 120.83 | 不可當實際 context 節省；只能描述特定歷史靜態文字集合 |
| 60% smaller output | 1 − 2,597 / 6,421 = 59.55% | 算術成立；原始 fixture 不在 repo，不能獨立重現；不得直接等同精確 token 降幅 |
| 96% vs raw API | 1 − 2,597 / 41,567 = 93.75% | 五操作總數應約 **94%**，不是 96%；若 96% 指特定案例，必須明確標示 |
| 12.8x latency | 26,653 / 2,082 = 12.80 | 算術成立；歷史數據未重新驗證，且腳本接受錯誤回應 |
| 約 49 秒 / 10 calls | (26,653 − 2,082) / 5 × 10 = 49,142 ms | 同樣依賴歷史 workload 與量測邊界，不能泛化到所有 agent/MCP |

Docker 官方文件確有 `--long-lived` 與 `--static` 選項。因此公平比較至少應分開標示 ephemeral 與 persistent 配置，不能從單一 Docker 配置推論 MCP 整體性能：https://docs.docker.com/reference/cli/docker/mcp/gateway/run/

## 手動與 AI 使用體驗建議

- Quick Start 補可複製的 config 目錄建立步驟，以及第一個唯讀成功例子與預期輸出；目前從安裝直接跳到手動寫 config。
- 增加 `atlas doctor` 或明確的 read-only credential/connectivity 檢查，區分 token 錯誤、site URL、權限與 optional fields。
- AI snippet 把 `atlas jira fields --search` 補成帶參數的例子；提示用子指令 help 探索 flags，因 group help 只列命令。
- 提供一次簡短的「搜尋 issue → 讀詳細內容」與「搜尋 page → 讀內容」示範；把認證、PATH 與 sandbox 網路限制的排錯集中。
- 現有 26 個測試主要涵蓋 Markdown rendering、optional field helper 與 Jira get；CI 沒有安裝套件與 CLI smoke test，未涵蓋上述 benchmark、分頁、Confluence reader 與 publish orchestration。
- Claude Code 的 AGENTS.md fallback 在現行官方文件有依據，不能一概當錯誤；建議標示支援版本與檢查載入的方法：https://code.claude.com/docs/en/memory#agentsmd

## 推廣前驗收門檻

1. 修正 benchmark 成功判斷、README 免安裝指令、圖表失敗發布與 Confluence 內容遺失。
2. 將首頁「121x／60%／12x」降為附條件歷史結果，並修正 96% 的總數算術錯誤；或以新的可重現數據替換。
3. 補公開 synthetic fixtures、同功能比較、內容完整性檢查與版本固定的測量記錄。時間測試交錯執行兩種方法，區分 warm-up 與穩態。
4. 發行修正版，於乾淨環境重新走一次 install → config → 唯讀操作 → AI 指令探索。Windows/Linux 安裝 smoke test 加入 CI。

在重新測量之前，適合對外的定位是「為終端機與 coding agents 提供精簡 Markdown 輸出的 Jira／Confluence CLI，可直接透過 shell 使用」。不宜宣稱全面取代 73 個工具、所有 MCP 都較慢，或保證固定 token 節省比例。

## 未驗證範圍

沒有使用真實 Jira/Confluence fixture 重新跑 live latency benchmark，也沒有對真實頁面／issue 執行寫入。沒有驗證各種 agent 的完整互動 session 或 Windows/Linux 實際終端環境。安裝與 help 成功不代表所有 Atlassian 操作均通過端到端測試；GitHub CI 綠燈亦不補足這些範圍。

## 後續修改紀錄

本報告上文保留審查當時狀態。使用者同意修改後，已撤下 README 倍數主標題、
修正安裝入口、重寫 benchmark 方法說明，並加入錯誤拒收、內容檢查、暖機、
交錯測量、原始 JSON 紀錄及輸出大小工具。另確認 raw API 基準缺少兩個操作，
因此 93.75% 只代表舊總數的算術關係，不能當成相同工作量的有效節省比例。
新的 live 數字尚未產生；上文的 Confluence 內容處理、發布與分頁問題仍待修正。
