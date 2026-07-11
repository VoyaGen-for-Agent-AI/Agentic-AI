from typing import TypedDict, Annotated, Sequence, Literal, Any, Dict, Optional
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # 儲存所有的對話紀錄
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # 使用者原始查詢
    user_query: str

    # Supervisor 決定的任務路由
    route: Literal["weather", "travel", "booking", "budget", "scheduler", "safety", "traffic", "multi", "unknown"]

    # 目前正在處理的任務描述
    current_task: str

    # 紀錄 Supervisor 決定要派發給誰 (例如: "travel", 或 "FINISH")
    next_step: str

    # 預算管家判斷出的預算階層 (窮遊 / 適中 / 寬裕)
    budget_tier: str

    # 各 stage (worker→coder→sandbox→parser) 完成後回傳給 supervisor 的結構化結果
    weather_result: dict[str, Any]
    movie_result: dict[str, Any]
    travel_result: dict[str, Any]
    booking_result: dict[str, Any]
    budget_result: dict[str, Any]
    traffic_result: dict[str, Any]
    scheduler_result: dict[str, Any]
    safety_result: dict[str, Any]
    traffic_result: dict[str, Any]

    # 每個 stage 執行完後附加的觀測紀錄 (stage 名稱 / 產生的 code / stdout / 狀態)
    # 使用 operator.add 讓平行的 travel / booking stage 可以安全合併，不會互相覆蓋
    stage_logs: Annotated[list[dict[str, Any]], operator.add]

    # Sandbox / action execution 相關欄位
    generated_code: str
    sandbox_stdout: str
    sandbox_stderr: str

    # --- 系統防護機制 ---
    # 紀錄發生錯誤時的追蹤訊息
    error_traceback: str

    # Critic Agent 的錯誤分類結果
    critic_result: Optional[Dict[str, Any]]

    # 執行狀態
    execution_status: Literal["success", "error", "timeout"]

    # 紀錄重試次數，避免無限迴圈
    retry_count: int

    # 最終回覆
    final_answer: str
