from typing import Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# 1. 定義 Prompt
SUPERVISOR_PROMPT = """
你是這個專業旅遊規劃團隊的主管，負責將使用者的請求精準路由給最適合的專員。
你的團隊有以下七位專員：
1. weather: 天氣專員。負責查詢目標城市的即時天氣、溫濕度與降雨機率。
2. travel: 行程規劃專員。負責發散思考，推薦景點清單（例如網美景點、歷史名勝等）。
3. booking: 訂房/預約專員。負責處理外部 API 調用，找尋特定區域（例如日月潭、台北101等景點周邊）的短期住宿與餐廳並進行比價。
4. budget: 預算估算專員。負責搜尋當地物價、匯率與平均花費，估算旅遊行程的總花費。
5. scheduler: 行程編輯員。負責將景點視為節點，計算點對點交通時間，並利用演算法思維排出最佳化移動路徑 (TSP)。
6. safety: 突發狀況官。負責處理負面邊界情況（如迷路、API 錯誤、行程超載），並觸發反思與修正機制。
7. traffic: 交通規劃專員。負責規劃起點、終點與停靠點之間的交通方式與車程時長。

請根據使用者的輸入，決定下一步該交給誰。如果已經完成所有任務，請回傳 "FINISH"。
只能從 ["weather", "travel", "booking", "budget", "scheduler", "safety", "traffic", "FINISH"] 中選擇一個回傳，不要回覆其他多餘的文字。
"""

# 2. 定義嚴格的輸出資料模型 (Pydantic)
class Route(BaseModel):
    next_step: Literal["weather", "travel", "booking", "budget", "scheduler", "safety", "traffic", "FINISH"] = Field(
        description="根據使用者意圖決定的下一步路由"
    )

# 3. 建立大腦節點邏輯
def create_supervisor_node(llm: ChatOpenAI):
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUPERVISOR_PROMPT),
        ("user", "{input}")
    ])
    
    # 這裡的 .with_structured_output(Route)會強制 OpenAI 只吐出符合 Route 格式的 JSON。
    supervisor_chain = prompt | llm.with_structured_output(Route)
    return supervisor_chain