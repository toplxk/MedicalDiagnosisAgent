"""诊断Agent - 症状分析与初步诊断（多轮追问）"""

import re
import json
from agents.base_agent import BaseAgent
from tools import symptom_tool
from rag.retriever import retrieve


class DiagnosisAgent(BaseAgent):
    """负责症状诊断的Agent，支持多轮追问收集信息。"""

    REQUIRED_INFO = ["main_symptom", "duration", "symptom_features", "accompanying"]
    OPTIONAL_INFO = ["aggravating", "relieving", "medical_history", "age", "gender", "medications"]

    def __init__(self):
        super().__init__(name="DiagnosisAgent", prompt_file="diagnosis_agent.txt")
        self.collected_info: dict = {}
        self.round_count: int = 0

    def process(self, user_message: str, extracted_info: dict = None) -> str:
        self.round_count += 1

        if extracted_info:
            self.collected_info.update(extracted_info)

        self._extract_info_from_message(user_message)
        missing = self._get_missing_info()

        if self.round_count >= 3 and self.collected_info.get("main_symptom"):
            return self._generate_diagnosis()
        elif not missing and self.collected_info.get("main_symptom"):
            return self._generate_diagnosis()

        context = ""
        if self.collected_info:
            context = f"已收集的患者信息：{json.dumps(self.collected_info, ensure_ascii=False, default=str)}"

        if self.collected_info.get("main_symptom"):
            rag_result = retrieve(self.collected_info["main_symptom"])
            rag_context = rag_result.get("context", "")
            if rag_context:
                context += f"\n\n相关医学知识：\n{rag_context}"

        return self.chat_stream(user_message, extra_context=context, temperature=0.6)

    def _extract_info_from_message(self, message: str):
        msg = message.lower()

        symptom_keywords = {
            "头痛": "main_symptom", "头疼": "main_symptom",
            "头晕": "main_symptom", "恶心": "main_symptom",
            "呕吐": "main_symptom", "腹痛": "main_symptom",
            "肚子疼": "main_symptom", "胸闷": "main_symptom",
            "胸痛": "main_symptom", "咳嗽": "main_symptom",
            "发热": "main_symptom", "发烧": "main_symptom",
            "腰痛": "main_symptom", "关节痛": "main_symptom",
            "失眠": "main_symptom", "乏力": "main_symptom",
            "心悸": "main_symptom", "气短": "main_symptom",
            "腹泻": "main_symptom", "便秘": "main_symptom",
        }
        for keyword, field in symptom_keywords.items():
            if keyword in msg and "main_symptom" not in self.collected_info:
                self.collected_info[field] = keyword

        time_keywords = {
            "今天": "今天", "昨天": "昨天", "前天": "前天",
            "一周": "一周", "两周": "两周", "一个月": "一个月",
            "几天": "几天", "很久": "很久",
        }
        for kw, val in time_keywords.items():
            if kw in msg and "duration" not in self.collected_info:
                self.collected_info["duration"] = val

        if ("男" in msg or "先生" in msg) and "gender" not in self.collected_info:
            self.collected_info["gender"] = "男"
        elif ("女" in msg or "女士" in msg) and "gender" not in self.collected_info:
            self.collected_info["gender"] = "女"

        age_match = re.search(r'(\d{1,3})\s*岁', msg)
        if age_match and "age" not in self.collected_info:
            self.collected_info["age"] = int(age_match.group(1))

    def _get_missing_info(self) -> list[str]:
        return [f for f in self.REQUIRED_INFO if f not in self.collected_info]

    def _generate_diagnosis(self) -> str:
        symptom_info = ""
        if self.collected_info.get("main_symptom"):
            result = symptom_tool.lookup_symptom(self.collected_info["main_symptom"])
            if result.get("success"):
                symptom_info = json.dumps(result["data"], ensure_ascii=False)

        rag_context = ""
        if self.collected_info.get("main_symptom"):
            rag_result = retrieve(self.collected_info["main_symptom"])
            rag_context = rag_result.get("context", "")

        diagnosis_request = f"""请根据以下患者信息进行诊断分析：

患者信息：
{json.dumps(self.collected_info, ensure_ascii=False, default=str)}

症状相关数据：
{symptom_info}

相关医学知识：
{rag_context}

请按照诊断分析报告格式输出。"""

        response = self.chat_stream(diagnosis_request, temperature=0.5)
        self._reset_state()
        return response

    def _reset_state(self):
        self.collected_info.clear()
        self.round_count = 0
        self.history.clear()
