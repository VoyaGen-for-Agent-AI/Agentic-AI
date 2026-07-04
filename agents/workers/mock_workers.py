from core.state import AgentState
from langchain_core.messages import AIMessage

def weather_node(state: AgentState):
    weather_result = {
        "location": "Taipei",
        "condition": "rainy",
        "rain_probability": 80,
        "temperature": 28,
    }
    return {
        "weather_result": weather_result,
        "messages": [
            AIMessage(content="[Mock][Weather] Taipei 目前為 rainy，降雨機率 80%，氣溫 28 度。")
        ]
    }

def travel_node(state: AgentState):
    travel_result = {
        "destination": "Taipei",
        "duration": "1 day",
        "spots": ["Taipei 101", "Chiang Kai-shek Memorial Hall", "Ximending"],
        "transportation": "MRT",
    }
    return {
        "travel_result": travel_result,
        "messages": [
            AIMessage(content="[Mock][Travel] Taipei 1 day 行程包含 Taipei 101、Chiang Kai-shek Memorial Hall、Ximending，建議搭 MRT。")
        ]
    }

def movie_node(state: AgentState):
    movie_result = {
        "title": "Inception",
        "genre": "sci-fi",
        "rating": 8.8,
        "recommendation_reason": "適合喜歡燒腦劇情的使用者",
    }
    return {
        "movie_result": movie_result,
        "messages": [
            AIMessage(content="[Mock][Movie] 推薦 Inception，類型是 sci-fi，評分 8.8，適合喜歡燒腦劇情的使用者。")
        ]
    }
