from core.state import AgentState
from langchain_core.messages import AIMessage

def weather_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 已為您取得目標城市的氣溫與降雨機率。")]}

def travel_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 已為您整理好符合偏好的特色景點清單！")]}

def booking_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 已為您比價並整理出大學周邊的推薦住宿與餐廳。")]}

def financial_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 預算管家已完成匯率轉換，並更新剩餘可用預算額度。")]}

def scheduler_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 行程編輯員已計算出最佳移動路徑 (TSP) 並排定時間表。")]}

def safety_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 突發狀況官已為您檢查行程合理性，並提供備案。")]}