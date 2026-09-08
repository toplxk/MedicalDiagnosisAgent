"""咨询Agent - 基于RAG的医疗知识问答"""

from agents.base_agent import BaseAgent
from rag.retriever import retrieve


class ConsultationAgent(BaseAgent):
    """负责医疗知识咨询的Agent，集成RAG检索。"""

    def __init__(self):
        super().__init__(name="ConsultationAgent", prompt_file="consultation_agent.txt")

    def process(self, user_message: str, echo: bool = True) -> str:
        rag_result = retrieve(user_message)
        context = rag_result.get("context", "")

        if context:
            return self.chat_stream(user_message, extra_context=context, temperature=0.7, echo=echo)
        return self.chat_stream(user_message, temperature=0.7, echo=echo)
