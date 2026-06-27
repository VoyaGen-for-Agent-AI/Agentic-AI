from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # 儲存所有的對話紀錄
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # 紀錄 Supervisor 決定要派發給誰 (例如: "weather", "travel", "movie", 或 "FINISH")
    next_step: str
    
    # 紀錄發生錯誤時的追蹤訊息
    error_traceback: str
    
    # 紀錄重試次數，避免無限迴圈
    retry_count: int