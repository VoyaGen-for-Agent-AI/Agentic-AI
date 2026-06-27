from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI # 假設你用 OpenAI
from core.state import AgentState

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

# 2. 建立路由判斷邏輯
def create_supervisor_node(llm: ChatOpenAI):
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUPERVISOR_PROMPT),
        ("user", "{input}")
    ])
    
    # 這裡會串接 LLM，並限制它只能輸出我們規定的幾個單字
    supervisor_chain = prompt | llm 
    return supervisor_chain