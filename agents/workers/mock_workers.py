from core.state import AgentState
from langchain_core.messages import AIMessage

def weather_node(state: AgentState):
    # 假裝已經查好天氣，並將訊息包裝成 AI 回覆加進去
    return {"messages": [AIMessage(content="[Mock] 台北明天天氣晴朗，降雨機率 10%")]}

def travel_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 已為您排好陽明山一日遊的完美行程！")]}

def movie_node(state: AgentState):
    return {"messages": [AIMessage(content="[Mock] 推薦您觀看 Netflix 的強檔影集！")]}