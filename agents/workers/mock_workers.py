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

def booking_node(state: AgentState):
    booking_result = {
        "location": "Taipei 101",
        "hotels": ["W Hotel Taipei", "Robertson Suites"],
        "restaurants": ["Din Tai Fung", "Shin Yeh"],
        "price_comparison": "住宿均價 NT$3,500/晚，已篩選出評價最高的 2 間",
    }
    return {
        "booking_result": booking_result,
        "messages": [
            AIMessage(content="[Mock][Booking] 已為您比價並整理出 Taipei 101 周邊的推薦住宿與餐廳。")
        ]
    }

def financial_node(state: AgentState):
    financial_result = {
        "budget_total": 20000.0,
        "budget_remaining": 12500.0,
        "currency": "TWD",
        "exchange_rate_to_usd": 0.031,
    }
    return {
        "financial_result": financial_result,
        "messages": [
            AIMessage(content="[Mock][Financial] 預算管家已完成匯率轉換，剩餘可用預算為 NT$12,500。")
        ]
    }

def scheduler_node(state: AgentState):
    scheduler_result = {
        "itinerary": ["Taipei 101", "Ximending", "Chiang Kai-shek Memorial Hall"],
        "total_travel_time_minutes": 95,
        "algorithm": "TSP nearest-neighbor",
    }
    return {
        "scheduler_result": scheduler_result,
        "messages": [
            AIMessage(content="[Mock][Scheduler] 行程編輯員已計算出最佳移動路徑 (TSP)，總移動時間約 95 分鐘。")
        ]
    }

def safety_node(state: AgentState):
    safety_result = {
        "status": "ok",
        "issues": [],
        "fallback_suggestion": "目前行程無異常，若迷路可撥打當地緊急聯絡電話。",
    }
    return {
        "safety_result": safety_result,
        "messages": [
            AIMessage(content="[Mock][Safety] 突發狀況官已檢查行程合理性，目前狀態正常。")
        ]
    }
