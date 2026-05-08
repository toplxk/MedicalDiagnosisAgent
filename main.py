"""医疗诊断多Agent交互系统 - 主入口"""

import os
import sys

from agents.router_agent import RouterAgent
from agents.appointment_agent import AppointmentAgent
from agents.queue_agent import QueueAgent
from agents.consultation_agent import ConsultationAgent
from agents.diagnosis_agent import DiagnosisAgent
from rag.vector_store import add_documents, get_collection_count, clear_collection
from config import MEDICAL_DOCS_DIR


class MedicalSystem:
    """医疗诊断多Agent系统。"""

    def __init__(self):
        self.router = RouterAgent()
        self.agents = {
            "appointment": AppointmentAgent(),
            "queue": QueueAgent(),
            "consultation": ConsultationAgent(),
            "diagnosis": DiagnosisAgent(),
        }
        self.current_agent = None  # 当前活跃的Agent

    def init_rag(self):
        """初始化RAG：将医疗文档加载到向量数据库。"""
        if get_collection_count() > 0:
            print(f"[RAG] 向量数据库已有 {get_collection_count()} 条文档，跳过初始化。")
            return

        print("[RAG] 正在初始化医疗知识库...")
        doc_files = []
        if os.path.exists(MEDICAL_DOCS_DIR):
            for filename in os.listdir(MEDICAL_DOCS_DIR):
                if filename.endswith(".txt"):
                    filepath = os.path.join(MEDICAL_DOCS_DIR, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    doc_files.append((filename, content))

        if not doc_files:
            print("[RAG] 未找到医疗知识文档，跳过初始化。")
            return

        total_chunks = 0
        for filename, content in doc_files:
            # 按段落分块
            chunks = self._split_into_chunks(content, chunk_size=500, overlap=50)
            if not chunks:
                continue

            metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]
            ids = [f"{filename}_{i}" for i in range(len(chunks))]
            add_documents(chunks, metadatas, ids)
            total_chunks += len(chunks)

        print(f"[RAG] 初始化完成，共加载 {len(doc_files)} 个文档，{total_chunks} 个片段。")

    @staticmethod
    def _split_into_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """将文本分割为重叠的片段。

        Args:
            text: 原始文本
            chunk_size: 每个片段的最大字符数
            overlap: 片段之间的重叠字符数

        Returns:
            文本片段列表
        """
        # 先按段落分割
        paragraphs = text.split("\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                if current_chunk and len(current_chunk) > 50:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n"

        if current_chunk.strip() and len(current_chunk.strip()) > 50:
            chunks.append(current_chunk.strip())

        return chunks

    def process_message(self, user_message: str):
        """处理用户消息（Agent通过流式直接打印，闲聊/澄清通过print输出）。"""
        # 如果当前有活跃Agent且正在进行多轮对话，继续由该Agent处理
        if self.current_agent and self.current_agent in ["diagnosis"]:
            agent = self.agents[self.current_agent]
            intent_check = self.router.classify_intent(user_message)
            intent = intent_check.get("intent", "")

            if intent not in ("diagnosis", "chitchat") and intent_check.get("confidence", 0) > 0.7:
                self.current_agent = None
                self.agents["diagnosis"]._reset_state()
            else:
                agent.process(user_message, intent_check.get("extracted_info", {}))
                return

        # Router分析意图
        route_result = self.router.classify_intent(user_message)
        intent = route_result.get("intent", "chitchat")
        needs_clarification = route_result.get("needs_clarification", False)
        clarification_question = route_result.get("clarification_question")
        extracted_info = route_result.get("extracted_info", {})

        # 需要澄清
        if needs_clarification and clarification_question:
            print(f"\n[助手] {clarification_question}")
            return

        # 闲聊
        if intent == "chitchat":
            print(f"\n[助手] {self._handle_chitchat(user_message)}")
            return

        # 路由到对应Agent
        agent = self.agents.get(intent)
        if not agent:
            print("\n[助手] 抱歉，我暂时无法处理这类请求。请问您需要预约挂号、排队叫号、医疗咨询还是症状诊断服务？")
            return

        # 设置当前活跃Agent（用于多轮对话）
        if intent == "diagnosis":
            self.current_agent = "diagnosis"

        # 调用Agent处理（内部流式输出）
        if intent in ("appointment", "queue"):
            agent.process(user_message, extracted_info)
        else:
            agent.process(user_message)

    @staticmethod
    def _handle_chitchat(user_message: str) -> str:
        """处理闲聊消息。"""
        msg = user_message.strip()

        greetings = ["你好", "hi", "hello", "嗨", "您好", "hey"]
        thanks = ["谢谢", "感谢", "多谢", "thanks", "thank"]
        bye = ["再见", "拜拜", "bye", "退出", "结束", "quit", "exit"]

        for g in greetings:
            if g in msg.lower():
                return ("您好！我是智能医疗助手，可以为您提供以下服务：\n"
                        "  1. 预约挂号 - 帮您预约医生门诊\n"
                        "  2. 排队叫号 - 管理您的就诊排队\n"
                        "  3. 医疗咨询 - 回答健康相关问题\n"
                        "  4. 症状诊断 - 根据症状提供初步分析\n"
                        "请问您需要什么帮助？")

        for t in thanks:
            if t in msg.lower():
                return "不客气！如果还有其他问题，随时可以问我。祝您身体健康！"

        for b in bye:
            if b in msg.lower():
                return "再见！祝您身体健康，如有需要随时联系。"

        return ("我是您的智能医疗助手，可以帮您：\n"
                "  - 预约挂号：「我想预约明天看内科」\n"
                "  - 排队叫号：「帮我取个号」\n"
                "  - 医疗咨询：「高血压是什么病？」\n"
                "  - 症状诊断：「我最近总是头晕恶心」\n"
                "请问您需要什么帮助？")

    def reset(self):
        """重置系统状态。"""
        for agent in self.agents.values():
            agent.reset()
        self.current_agent = None
        self.router.reset()


def main():
    """主函数 - 启动交互循环。"""
    print("=" * 60)
    print("       智能医疗诊断多Agent交互系统")
    print("=" * 60)
    print()

    # 初始化系统
    system = MedicalSystem()

    # 初始化RAG知识库
    try:
        system.init_rag()
    except Exception as e:
        print(f"[RAG] 初始化失败（{e}），系统仍可使用，但检索功能可能不可用。")

    print()
    print("系统已就绪！输入问题开始对话，输入 'quit' 或 '退出' 结束。")
    print("-" * 60)

    while True:
        try:
            user_input = input("\n[用户] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！祝您身体健康！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "退出", "结束"):
            print("再见！祝您身体健康！")
            break

        if user_input.lower() in ("reset", "重置"):
            system.reset()
            print("[系统] 对话已重置。")
            continue

        # 处理用户消息（Agent内部已流式输出）
        system.process_message(user_input)


if __name__ == "__main__":
    main()
