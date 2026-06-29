from typing import Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# 1. 定義 Prompt
SUPERVISOR_PROMPT = """
你是這個團隊的主管，負責將使用者的請求路由給最適合的專員。
你的團隊有以下三位專員：
1. weather: 負責查詢天氣資訊。
2. movie: 負責查詢電影或 Netflix 影集。
3. travel: 負責規劃旅遊行程與計算交通時間。

請根據使用者的輸入，決定下一步該交給誰。如果已經完成所有任務，請回傳 "FINISH"。
只能從 ["weather", "travel", "movie", "FINISH"] 中選擇一個回傳，不要回覆其他多餘的文字。
"""

# 2. 定義嚴格的輸出資料模型 (Pydantic)
class Route(BaseModel):
    next_step: Literal["weather", "travel", "movie", "FINISH"] = Field(
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