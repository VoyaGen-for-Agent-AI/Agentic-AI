# VoyaGen

# Agentic AI Project (LangGraph)

本專案使用 LangGraph 構建 Agent 工作流，並採用 FastAPI 作為後端伺服器。
為確保團隊開發環境一致，統一使用 **Poetry** 進行套件與虛擬環境管理。

## 🚀 開發環境建置指南 (Quick Start)

### Step 1: 安裝基礎工具
請確保你的電腦已安裝 Python (建議 3.12 以上) 與 Poetry。
若尚未安裝 Poetry，請在終端機執行：
`pip install poetry`

### Step 2: 一鍵同步開發環境
請將專案 Clone 到本機後，在專案根目錄下執行以下指令。
Poetry 會自動讀取 `poetry.lock`，並為你建立獨立的虛擬環境，精準安裝所有套件：
`poetry install`

### Step 3: 設定金鑰 (環境變數)
本專案會用到多組外部 API，請設定你本機的金鑰：
1. 在專案根目錄找到 `.env.example` 檔案。
2. 複製一份該檔案，並將檔名重新命名為 `.env`。
3. 打開 `.env`，填入對應的 API Keys（如 OpenAI, Langfuse, E2B 等）。
> ⚠️ **注意**：`.env` 已加入 `.gitignore`，請絕對不要將真實的 API Key 提交到 Git 上！
註:這個還沒有加任何api

### Step 4: 執行測試與啟動伺服器

**✅ 執行單元測試 (確認環境正常)：**
`poetry run pytest tests/`

**🔥 啟動 FastAPI 本機開發伺服器：**
`poetry run uvicorn main:app --reload`
註:這個還沒有處理

## Sprint 1 Role B 交付說明

Role B 本週負責 Action & Sandbox Integration 的最小可交付骨架，Sprint 1 先以 Mock Worker 完成可運作流程，不串接真實外部 API。

目前已完成：

- Weather / Travel / Booking / Financial / Scheduler / Safety 六個 mock workers。
- Workers 接收 `AgentState`，並回傳 LangGraph 可合併的 state update。
- Workers 回傳 `messages` 與未來可替換真 API 的結構化結果：
  - `weather_result`
  - `travel_result`
  - `booking_result`
  - `financial_result`
  - `scheduler_result`
  - `safety_result`
- `final_response_node` 可將 worker result 整理成 `final_answer`。
- LangGraph workflow 已接成 `Supervisor -> Mock Worker -> Final Response -> END`。
- Langfuse callback 已接入主要 `app_graph.invoke` 流程。

### Role B 測試方式

一般單元測試不需要任何 API key，也不會呼叫真實 Weather / Movie / Travel API：

`poetry run pytest`

Mock worker 測試：

`poetry run pytest tests/test_mock_workers.py`

Final response 測試：

`poetry run pytest tests/test_final_response.py`

### Langfuse Trace 手動驗證

若要確認 Langfuse 後台可看到 `User -> Supervisor -> Mock Worker -> Final Response` trace，請先在 `.env` 設定：

- `OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`

然後執行：

`poetry run python scripts/test_langfuse_trace.py`

腳本會使用測試 query「幫我查天氣」，執行現有 workflow，印出 final answer，並提醒到 Langfuse dashboard 查看 trace。

### Sprint 1 暫不處理

以下項目保留到 Sprint 2 或後續：

- 真實 Weather / Movie / Travel API 串接。
- E2B sandbox 真實程式執行。
- Critic Agent。
- Tavily / OpenWeather / Google Maps / TMDB 等外部服務整合。
