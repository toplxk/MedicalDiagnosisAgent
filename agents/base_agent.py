"""Agent基类 - 提供LLM调用、对话历史管理等基础能力"""

import os
import sys
from utils.llm_client import chat, chat_stream
from config import PROMPTS_DIR


class BaseAgent:
    """所有Agent的基类。"""

    def __init__(self, name: str, prompt_file: str):
        self.name = name
        self.system_prompt = self._load_prompt(prompt_file)
        self.history: list[dict] = []

    @staticmethod
    def _load_prompt(filename: str) -> str:
        filepath = os.path.join(PROMPTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()

    def _build_messages(self, user_message: str, extra_context: str = None) -> list[dict]:
        """构建完整的消息列表。"""
        messages = [{"role": "system", "content": self.system_prompt}]
        if extra_context:
            messages.append({
                "role": "system",
                "content": f"以下是参考信息，请结合这些信息回答用户问题：\n\n{extra_context}",
            })
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def chat(self, user_message: str, extra_context: str = None, temperature: float = 0.7) -> str:
        """非流式对话调用。"""
        messages = self._build_messages(user_message, extra_context)
        response = chat(messages, temperature=temperature)
        self._update_history(user_message, response)
        return response

    def chat_stream(self, user_message: str, extra_context: str = None, temperature: float = 0.7) -> str:
        """流式对话调用，逐token打印并返回完整回复。

        Returns:
            模型完整回复
        """
        messages = self._build_messages(user_message, extra_context)
        full_response = ""
        print("\n[助手] ", end="", flush=True)
        for chunk in chat_stream(messages, temperature=temperature):
            print(chunk, end="", flush=True)
            full_response += chunk
        print()  # 换行
        self._update_history(user_message, full_response)
        return full_response

    def _update_history(self, user_message: str, response: str):
        """更新对话历史。"""
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def reset(self):
        self.history.clear()
