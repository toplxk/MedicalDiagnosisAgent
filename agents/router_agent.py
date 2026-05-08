"""路由Agent - 意图识别与分发"""

import json
from agents.base_agent import BaseAgent
from config import PROMPTS_DIR


class RouterAgent(BaseAgent):
    """负责识别用户意图并路由到相应Agent。"""

    def __init__(self):
        super().__init__(name="RouterAgent", prompt_file="router_agent.txt")

    def classify_intent(self, user_message: str) -> dict:
        """分析用户意图。

        Returns:
            {"intent": str, "confidence": float, "needs_clarification": bool,
             "clarification_question": str|None, "extracted_info": dict}
        """
        response = self.chat(user_message, temperature=0.3)

        # 解析JSON响应
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return result
        except (json.JSONDecodeError, KeyError):
            pass

        # 解析失败时返回默认
        return {
            "intent": "chitchat",
            "confidence": 0.3,
            "needs_clarification": True,
            "clarification_question": "抱歉，我没有完全理解您的意思。请问您是想要：1.预约挂号 2.排队叫号 3.医疗咨询 4.症状诊断？",
            "extracted_info": {},
        }
