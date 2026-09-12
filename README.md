# VoyaGen

以 **LangGraph** 建構的多 Agent 旅遊規劃系統。使用者用一句自然語言描述需求，系統拆解成
解析、天氣、景點、訂房、交通、行程、驗證、預算等多個專員協作，最後輸出一份完整的中文行程建議。

後端為 FastAPI，前端為 Vue 3，LLM 透過 OpenRouter 取得，程式碼驗證在 E2B 遠端沙盒執行，
全流程以 Langfuse 追蹤。

---

## 系統架構

### 執行流程

`main.py` 編譯出的 `app_graph` 是一條線性 pipeline，每個節點都是 LangGraph 的一個 node：

```
使用者輸入
  └─ trip_parser      規則式解析：目的地 / 日期 / 天數 / 人數 / 預算 / 偏好
  └─ weather          天氣與戶外風險評估
  └─ spot             景點推薦（會參考 weather 的 outdoor_risk 重新排序）
  └─ booking          住宿推薦與比價
  └─ traffic          分段交通規劃與車資估算
  └─ travel           整合成逐日行程表
  └─ e2b_validation   在 E2B 沙盒執行 6 項一致性檢查
  └─ budget           預算配額與實際花費比對
  └─ final_response   組裝成中文長文回覆
```

### 三層降級與資料溯源

每個領域 agent 都有一條降級梯：**真實 API → LLM 生成 → 內建 mock**。
任一層失敗會自動退到下一層，流程不會中斷。

每筆結果都帶 `source` 與 `source_detail` 欄位（例如 `api_openweather_forecast`、
`tavily_search`、`llm`、`mock_fallback`）。將 `DEMO_SHOW_SOURCES=1` 時，最終回覆會附上
「資料來源摘要」，讓使用者清楚知道哪些數字是估計值。`tests/test_result_provenance.py`
會斷言整條溯源鏈，確保降級狀態始終是可見的。

### 子圖狀態隔離與平行化

`agents/stage_graph.py` 把 `worker → coder → e2b_sandbox → parser` 這條執行鏈包成
**獨立編譯的子圖**，中繼欄位（`generated_code`、`sandbox_stdout`、`execution_status`）
只存在於子圖內部，不會冒泡到父圖。父圖只看得到各自不同的 result key，以及用
`operator.add` 合併的 `messages` 與 `stage_logs`，因此平行分支不會互相覆蓋狀態。

若不做這層隔離，travel 與 booking 平行執行時會在同一個 superstep 同時寫入沒有 reducer 的
`generated_code`，LangGraph 會直接拋出 `InvalidUpdateError: At key 'generated_code':
Can receive only one value per step`。

`agents/supervisor.py` 提供一個**確定性**的調度器：用已完成的 stage 集合決定下一棒，
並可回傳 list 做平行 fan-out。它刻意不用 LLM 決定路由，也刻意用「有沒有跑過」而不是
「有沒有產出結果」判斷進度，確保某個 stage 失敗時流程仍會前進，不會無限重試。

> **這套架構與目前主線的關係**
>
> `app_graph` 目前走的是上方的線性流程。`agents/stage_graph.py` 與 `agents/supervisor.py`
> 這套子圖 + supervisor 架構，在 `5b6d352`（2026-07-11）到 `243eddd`（07-15）之間
> 曾經就是 `main.py` 的主圖。
>
> 07-15 我們把 demo 路徑換成現在的線性流程。子圖路徑的每個 stage 都依賴「LLM 當場產出
> 可執行的 Python」與「E2B 沙盒即時回應」這兩個外部條件，現場 demo 時等於兩個獨立的
> 失敗點；線性流程兩者都不需要，沒有任何金鑰也能跑完全程。我們選擇了現場的確定性，
> 代價是主線不再展示子圖與平行架構。
>
> 另外必須揭露：子圖鏈當時還有一個潛伏缺陷。LangGraph 會依節點函式第一個參數的型別
> 標註過濾輸入狀態，而 `parser_node` 標註的是 `AgentState`，其中並未宣告 `result_key`，
> 因此子圖裡的 parser 始終收不到寫入目標，回報 `Unable to determine result target.`，
> 等於這條鏈從未真正產出過結構化結果。此缺陷於 2026-09-12 為子圖補上一層標註為
> `StageState` 的 parser 包裝後修正，並由 `tests/test_stage_graph_isolation.py` 覆蓋。
>
> 那次改寫同時改變了 worker 的角色：原本 worker 產生一份需求規格交給 coder 寫程式
> （回傳 `messages` 與 `next_step="coder"`），改寫後 worker 直接自行產出結果
> （回傳 `*_result` 與下一個 stage 名稱）。六個 domain worker 中目前只有
> `schedule_worker.py` 仍是舊合約，因此 2026-09-12 把子圖的 worker 路由改成**兩種合約
> 都支援**：`next_step == "coder"` 才進產碼鏈，否則視為結果已備妥、直接結束子圖。
>
> 這套架構的端到端執行請跑 `scripts/manual_stage_graph_demo.py`，它會驗證六個 stage
> 是否跑完、travel / booking 是否真的在不同執行緒平行、以及中繼欄位有沒有外流。
>
> `scripts/manual_parallel_graph_demo.py` 是**另外獨立建圖**的平行 benchmark，並未使用
> 上述兩個模組；它的平行節點是注入固定延遲（`PARALLEL_DEMO_DELAY_SECONDS`，預設 0.5 秒）
> 的 mock，量測的是 LangGraph 的併發排程行為，不是子圖隔離的效果。

---

## 技術棧

| 層級 | 技術 |
|---|---|
| Agent 編排 | LangGraph 1.2（StateGraph、TypedDict 狀態、`operator.add` reducer、sub-graph） |
| LLM 接入 | LangChain 1.3 + `langchain-openai`，base_url 指向 OpenRouter |
| 程式碼執行 | E2B Code Interpreter 2.8（遠端 Ubuntu 沙盒） |
| 可觀測性 | Langfuse 4（以 LangChain CallbackHandler 注入） |
| 後端 | FastAPI 0.138 + Uvicorn |
| 前端 | Vue 3 + Vite + Tailwind CSS |
| 外部資料 | OpenWeather（forecast / current）、Tavily Search |
| 工程化 | Poetry、pytest、GitHub Actions CI |

---

## 快速開始

### 1. 安裝

需要 Python 3.12 以上與 Poetry。

```bash
pip install poetry
poetry install
```

### 2. 設定環境變數

```bash
cp .env.example .env
```

**所有金鑰都是選用的。** 不填任何金鑰也能完整跑完整條 pipeline，各 stage 會自動退回 mock。
各欄位的用途與影響請見 `.env.example` 內的註解。

> `.env` 已列入 `.gitignore`，請勿將真實金鑰提交到 Git。

### 3. 執行測試

單元測試不需要任何 API key，也不會呼叫任何外部服務：

```bash
poetry run pytest
```

目前共 169 支測試，並由 `.github/workflows/main.yml` 在每次 push 時於 CI 執行。

### 4. 啟動後端

```bash
poetry run uvicorn main:app --reload
```

提供 `GET /chat/{query}`，回傳 `{response, budget_tier, stages}`。
`stages` 內含每個 stage 的執行狀態與產出，可用於前端視覺化。

### 5. 啟動前端

```bash
cd frontend
npm install
cp .env.example .env    # 設定 VITE_USE_REAL_BACKEND 與 VITE_API_BASE_URL
npm run dev
```

前端預設在 `http://localhost:5173`，後端已在 CORS 白名單放行該來源。
畫面上可即時切換「真實後端」與「模擬資料」，方便在無網路的場合 demo。

---

## 手動驗證腳本

`scripts/` 下的腳本都以 `manual_` 開頭，需要真實金鑰，**不會**被 CI 執行。

| 腳本 | 用途 |
|---|---|
| `demo_run.py` | 用完整化的 DEMO_PROMPT 跑一次完整 pipeline，印出各 stage 紀錄與最終回覆 |
| `manual_stage_graph_demo.py` | 用 `stage_graph` + `supervisor` 跑完整架構，驗證平行 fan-out 與狀態隔離 |
| `manual_parallel_graph_demo.py` | 序列 vs 平行執行的 benchmark（自建圖與延遲 mock，不使用 `stage_graph` / `supervisor`） |
| `manual_langfuse_trace.py` | 確認 Langfuse 後台能看到完整 trace |
| `manual_e2b_smoke_test.py` | 確認 E2B 沙盒連線與程式碼執行正常 |
| `manual_e2b_error_handling_demo.py` | 展示沙盒執行失敗時的錯誤處理與降級 |
| `manual_critic_demo.py` | 展示 Critic Agent 的錯誤分類與修復建議 |
| `diagnose_stage.py` | 單獨跑某一個 stage，用於除錯 |

執行範例：

```bash
poetry run python scripts/demo_run.py
poetry run python scripts/manual_langfuse_trace.py
```

---

## 專案結構

```
main.py                      FastAPI 入口與主圖組裝
core/
  state.py                   AgentState：所有 agent 共用的資料契約
  sandbox.py                 E2B 沙盒封裝，含金鑰注入白名單
  observability.py           Langfuse callback 工廠
agents/
  supervisor.py              確定性調度器（含平行 fan-out）
  stage_graph.py             stage 子圖工廠與狀態隔離
  final_response.py          最終回覆組裝與資料來源摘要
  workers/                   各領域 agent 與 coder / sandbox / parser 執行鏈
prompts/                     各 agent 的 system prompt
tests/                       169 支單元測試
scripts/                     手動驗證與 demo 腳本
frontend/                    Vue 3 + Vite 前端
```

### 安全性設計

`core/sandbox.py` 的 `SANDBOX_ENV_ALLOWLIST` 只會把 `OPENWEATHER_API_KEY` 與
`TAVILY_API_KEY` 兩個「資料類」金鑰注入沙盒。`OPENAI_API_KEY`、`E2B_API_KEY`、
`LANGFUSE_*` 一律不注入，因為沙盒內執行的是 LLM 即時生成的程式碼，不應接觸到
能產生費用或寫入追蹤系統的憑證。
