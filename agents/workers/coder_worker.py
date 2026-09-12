import os
import re
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.coder_prompt import CODER_SYSTEM_PROMPT 
import time


# OpenRouter 對同一把 API key 的連續請求有 rate limit。早期各 stage 走免費模型
# (model 名稱帶 :free) 時連續呼叫會收到 429，因此這裡加了一段固定 5 秒的保守節流。
# 改用付費 provider 後已不需要，故預設關閉；若要切回免費模型做 demo，
# 在 .env 設 LLM_THROTTLE_SECONDS=5 即可恢復原本行為。
def _throttle_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("LLM_THROTTLE_SECONDS", "0")))
    except ValueError:
        return 0.0


def coder_node(state: AgentState):
    print("[Coder Agent] 接收到需求，開始撰寫程式碼...")
    throttle = _throttle_seconds()
    if throttle:
        time.sleep(throttle)
    
    # 1. 初始化 Coder 的專屬大腦
    # llm = ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     #model="google/gemma-4-26b-a4b-it:free",
    #     #model="liquid/lfm-2.5-1.2b-thinking:free",
    #     model="meta-llama/llama-3.3-70b-instruct:free",
    #     #model="openai/gpt-oss-20b:free",
    #     api_key=os.getenv("OPENAI_API_KEY") # type: ignore
    # )
    ##############付費#################
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        model="meta-llama/llama-3.3-70b-instruct",
        api_key=os.getenv("OPENAI_API_KEY"), # type: ignore
        extra_body={
            "provider": {
                "order": ["DeepInfra"],
                "ignore": ["Nebius Token Factory","AkashML","NovitaAI","Parasail","SambaNova Turbo","Groq","Weight&Biases","Google Vertex", "Together","Cloudflare"],
                "allow_fallbacks": True
            }
        } 
    )
    ################################# 

    # 2. 抓取上一位專員 (如 Weather Worker) 提出的需求
    #    這行原本直接下標且位於 try 區塊外，messages 不存在時會讓整張圖崩潰。
    messages = state.get("messages") or []
    if not messages:
        print("⚠️  [Coder Agent] 沒有可用的需求訊息，略過程式碼產生。")
        return {
            "next_step": "FINISH",
            "execution_status": "error",
            "error_traceback": "coder_node requires at least one message in state.",
        }
    last_request = messages[-1].content

    # 3. 組裝訊息交給 LLM
    messages = [
        SystemMessage(content=CODER_SYSTEM_PROMPT),
        HumanMessage(content=f"請根據以下需求撰寫 Python 程式碼：\n{last_request}")
    ]

    try:
        response = llm.invoke(messages)
        content = response.content

        # 4. 解析 Markdown 格式，只抽出 ```python ... ``` 裡面的純程式碼
        # 使用 re.DOTALL 讓正則表達式可以跨行比對
        match = re.search(r'```python\n(.*?)\n```', str(content), re.DOTALL)
        
        if match:
            clean_code = match.group(1)
        else:
            # 如果沒加 Markdown，就整包當作程式碼硬上
            clean_code = str(content) 

        print(f"✅  [Coder Agent] 程式碼撰寫完成！共 {len(clean_code)} 字元。")
        
        # 5. 更新狀態機
        # 注意：我們需要把生出來的 code 存進 State，讓下一個 E2B 節點可以讀取
        return {
            "generated_code": clean_code, 
            "next_step": "e2b_sandbox" # 寫完 code 後，下一步當然是去沙盒跑跑看
        }

    except Exception as e:
        print(f"⚠️  [Coder Agent] 發生錯誤: {e}")
        return {
            "next_step": "FINISH",
            "execution_status": "error",
            "error_traceback": str(e),
        }
