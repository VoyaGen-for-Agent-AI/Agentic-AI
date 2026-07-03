from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # 儲存所有的對話紀錄
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # 紀錄 Supervisor 決定要派發給誰 (例如: "travel", 或 "FINISH")
    next_step: str
    
    # --- 系統防護機制 ---
    # 紀錄發生錯誤時的追蹤訊息
    error_traceback: str
    
    # 紀錄重試次數，避免無限迴圈
    retry_count: int

    # --- 旅遊業務狀態 ---
    # 紀錄使用者目前查詢的目標城市或地點
    current_location: str
    
    # 存放天氣專員抓回來的結構化天氣資料
    weather_data: dict
    
    # 給預算專員使用的總預算剩餘額度
    budget_remaining: float
    
    # 給「行程編輯員」做演算法排程 (TSP) 的候選景點清單
    itinerary_nodes: list