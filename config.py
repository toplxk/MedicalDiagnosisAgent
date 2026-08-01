import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# LLM 配置
LLM_MODEL = "deepseek-v4-flash"
EMBEDDING_MODEL = "text-embedding-v3"

# RAG 配置
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "data", "chroma_db")
CHROMA_COLLECTION_NAME = "medical_knowledge"
RAG_TOP_K = 3

# 医疗知识文档目录
MEDICAL_DOCS_DIR = os.path.join(os.path.dirname(__file__), "data", "medical_docs")

# Agent 提示词目录
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
