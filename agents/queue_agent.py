"""叫号Agent - 处理排队叫号相关任务"""

import json
from agents.base_agent import BaseAgent
from tools import queue_tool


class QueueAgent(BaseAgent):
    """负责排队叫号的Agent。"""

    def __init__(self):
        super().__init__(name="QueueAgent", prompt_file="queue_agent.txt")

    def process(self, user_message: str, extracted_info: dict = None) -> str:
        context = ""
        if extracted_info:
            context = f"从用户之前的消息中已提取到的信息：{json.dumps(extracted_info, ensure_ascii=False)}"

        response = self.chat_stream(user_message, extra_context=context, temperature=0.5)

        tool_call = self._extract_tool_call(response)
        if tool_call:
            result = queue_tool.execute(tool_call["action"], tool_call["params"])
            tool_feedback = f"工具执行结果：{json.dumps(result, ensure_ascii=False)}"
            return self.chat_stream(tool_feedback, temperature=0.5)

        return response

    @staticmethod
    def _extract_tool_call(response: str) -> dict | None:
        try:
            json_start = response.find("```json")
            if json_start >= 0:
                json_start = response.find("{", json_start)
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
                data = json.loads(json_str)
                if "action" in data:
                    return data
        except (json.JSONDecodeError, KeyError):
            pass

        try:
            json_start = response.find('{"action"')
            if json_start >= 0:
                depth = 0
                for i in range(json_start, len(response)):
                    if response[i] == '{':
                        depth += 1
                    elif response[i] == '}':
                        depth -= 1
                        if depth == 0:
                            data = json.loads(response[json_start:i + 1])
                            if "action" in data:
                                return data
                            break
        except (json.JSONDecodeError, KeyError):
            pass

        return None
