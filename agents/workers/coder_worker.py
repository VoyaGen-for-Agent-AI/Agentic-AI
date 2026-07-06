import os
import re
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.state import AgentState
from prompts.coder_prompt import CODER_SYSTEM_PROMPT 
import time

def coder_node(state: AgentState):
    print("[Coder Agent] 接收到需求，開始撰寫程式碼...")
    time.sleep(5)
    
    # 1. 初始化 Coder 的專屬大腦
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        #model="google/gemma-4-26b-a4b-it:free",
        #model="liquid/lfm-2.5-1.2b-thinking:free",
        #model="meta-llama/llama-3.3-70b-instruct:free",
        model="openai/gpt-oss-20b:free",
        api_key=os.getenv("OPENAI_API_KEY") # type: ignore
    )
    ##############付費#################
    # llm = ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     model="meta-llama/llama-3.1-8b-instruct",
    #     api_key=os.getenv("OPENAI_API_KEY"), # type: ignore
    #     extra_body={
    #         "provider": {
    #             "order": ["DeepInfra","NovitaAI"],
    #             "ignore": ["Cloudflare","Groq"],
    #             "allow_fallbacks": True
    #         }
    #     } 
    # )
    ################################# 

    # 2. 抓取上一位專員 (如 Weather Worker) 提出的需求
    last_request = state["messages"][-1].content

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
        return {"next_step": "FINISH"}