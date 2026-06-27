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
