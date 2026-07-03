from core.state import AgentState
from langchain_core.messages import AIMessage

def weather_node(state: AgentState):
    user_input = state["messages"][-1].content
    return {
        "messages": [
            AIMessage(content=f"[Mock][Weather] 已收到：{user_input}。台北明天天氣晴朗，降雨機率 10%。")
        ]
    }

def travel_node(state: AgentState):
    user_input = state["messages"][-1].content
    return {
        "messages": [
            AIMessage(content=f"[Mock][Travel] 已收到：{user_input}。已為您排好陽明山一日遊的完美行程！")
        ]
    }

def movie_node(state: AgentState):
    user_input = state["messages"][-1].content
    return {
        "messages": [
            AIMessage(content=f"[Mock][Movie] 已收到：{user_input}。推薦您觀看 Netflix 的強檔影集！")
        ]
    }
