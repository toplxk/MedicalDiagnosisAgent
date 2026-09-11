# 智能医疗诊断多Agent交互系统

基于大语言模型的智能医疗诊断多Agent系统，通过自然语言对话为患者提供预约挂号、排队叫号、医疗咨询、症状诊断等一站式医疗服务。

支持 **CLI** 与 **Web 工作台（FastAPI + 前端）** 两种交互方式。

## 功能概览

| 功能 | 说明 | 示例 |
|------|------|------|
| 预约挂号 | 查询医生排班、预约/取消门诊 | "我想预约明天看内科" |
| 排队叫号 | 取号、查询排队进度、叫号 | "帮我取个号" |
| 医疗咨询 | 基于RAG的医学知识问答 | "高血压是什么病？" |
| 症状诊断 | 多轮对话采集信息，生成诊断分析 | "我最近总是头晕恶心" |

## 系统架构

```
用户输入
   │
   ▼
┌──────────────┐
│  RouterAgent │  ← 意图分类（5类）+ 置信度判断 + 模糊澄清
└──────┬───────┘
       │
   ┌───┴───┬────────┬──────────┐
   ▼       ▼        ▼          ▼
预约Agent 排队Agent 咨询Agent  诊断Agent
                    │          │
                    ▼          ▼
              ┌──────────────────┐
              │   RAG 管线       │
              │ 查询改写→多路检索 │
              │ →结果融合→LLM生成 │
              └──────────────────┘
                     │
              ┌──────┴──────┐
              │  ChromaDB   │
              │  向量数据库  │
              └─────────────┘
```

## 技术栈

- **AI 框架：** LangChain（langchain + langchain-community + langchain-core）
- **大语言模型：** 通义千问 qwen-plus（通过 LangChain ChatTongyi 封装）
- **文本向量化：** text-embedding-v3（通过 LangChain DashScopeEmbeddings 封装）
- **向量数据库：** ChromaDB（HNSW 索引，余弦相似度）
- **开发语言：** Python 3.10+

## 项目结构

```
MedicalDiagnosisAgent/
├── main.py                     # 系统入口，MedicalSystem 类 + CLI 交互
├── api/                        # FastAPI 接口层
│   ├── server.py               # 路由、静态资源、RAG 启动
│   ├── session.py              # 多会话状态管理
│   └── schemas.py              # Pydantic 模型
├── frontend/                   # Web 工作台前端
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── db/                         # MySQL 数据层
│   ├── connection.py           # 连接与建库
│   ├── schema.py               # DDL + 科室/医生种子
│   └── __init__.py
├── config.py                   # 全局配置（API Key、模型名、路径、MySQL）
├── requirements.txt            # 依赖清单
├── .env                        # API 密钥（需自行配置）
│
├── agents/                     # Agent 模块
│   ├── base_agent.py           # 基类：LLM 调用、对话历史、流式输出
│   ├── router_agent.py         # 意图路由 Agent（JSON 格式分类输出）
│   ├── appointment_agent.py    # 预约挂号 Agent（工具调用）
│   ├── queue_agent.py          # 排队叫号 Agent（工具调用）
│   ├── consultation_agent.py   # 医疗咨询 Agent（RAG 增强）
│   └── diagnosis_agent.py      # 症状诊断 Agent（多轮对话 + RAG）
│
├── rag/                        # RAG 检索增强生成
│   ├── embedding.py            # DashScope 向量化封装
│   ├── vector_store.py         # ChromaDB 封装（增删查）
│   ├── query_rewriter.py       # LLM 查询改写（口语→专业术语）
│   └── retriever.py            # 检索器：改写→多路检索→融合
│
├── tools/                      # 业务工具（预约/排队走 MySQL）
│   ├── appointment_tool.py     # 科室/医生/排班/预约 CRUD
│   ├── patient_tool.py         # 患者档案管理
│   ├── queue_tool.py           # 排队系统
│   └── symptom_tool.py         # 症状→疾病映射（25 种症状，含危重分级）
│
├── prompts/                    # Agent 系统提示词
│   ├── router_agent.txt
│   ├── appointment_agent.txt
│   ├── queue_agent.txt
│   ├── consultation_agent.txt
│   └── diagnosis_agent.txt
│
└── data/
    ├── chroma_db/              # ChromaDB 持久化存储
    └── medical_docs/           # 医学知识文档（5 份）
        ├── common_diseases.txt # 常见疾病（高血压、糖尿病等 7 种）
        ├── department_guide.txt# 科室导诊（20+ 科室）
        ├── health_tips.txt     # 健康建议
        ├── medication_info.txt # 用药指南
        └── symptom_guide.txt   # 症状分析（含危险信号标识）
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- 通义千问 API Key（[申请地址](https://dashscope.console.aliyun.com/)）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

在项目根目录创建 `.env` 文件：

```env
QIANWEN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# MySQL（科室/医生/排班/预约/排队持久化）
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=meddesk
```

首次启动会自动建库建表并写入科室/医生种子数据。

### 4. 启动系统

**CLI：**

```bash
python main.py
```

首次启动会自动将 `data/medical_docs/` 下的医学文档加载到 ChromaDB 向量库，后续启动检测到已有数据则跳过。

**Web 工作台（推荐）：**

```bash
# 安装 Web 依赖（若尚未安装）
pip install -r requirements.txt

# 启动服务
python -m api.server
# 或
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://127.0.0.1:8000 即可使用三栏导诊工作台：

- 左：服务轨（对话 / 预约 / 排队 / 咨询 / 诊断）
- 中：对话区 + 意图路由徽章
- 右：排班查询、快速取号、诊断采集进度

API 文档：http://127.0.0.1:8000/docs

### 5. 主要 HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 多平台登录（password/phone/wechat/dingtalk） |
| POST | `/api/auth/register` | 账号注册 |
| POST | `/api/auth/sms` | 发送验证码（演示 123456） |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/platforms` | 支持的登录平台 |
| POST | `/api/chat` | 对话（自动意图路由） |
| POST | `/api/session/reset` | 重置会话 |
| GET | `/api/departments` | 科室列表 |
| GET | `/api/doctors` | 医生列表 |
| POST | `/api/schedule` | 查询排班 |
| POST | `/api/appointments` | 创建预约（登录后关联 user_id） |
| POST | `/api/appointments/query` | 查询预约 |
| POST | `/api/appointments/cancel` | 取消预约 |
| POST | `/api/queue/take` | 取号（登录后关联 user_id） |
| GET | `/api/queue/{department}` | 队列状态 |
| GET | `/api/health` | 健康检查 / RAG 状态 |
| GET | `/api/symptoms` | 常见症状列表 |

演示账号：`admin/admin123`、`zhangsan/123456`、`doctor/123456`；手机验证码固定 `123456`；微信/钉钉授权码任意字符串即可（首次自动开户）。

### 6. CLI 交互命令

| 命令 | 说明 |
|------|------|
| 直接输入问题 | 系统自动识别意图并分发处理 |
| `reset` / `重置` | 重置当前对话状态 |
| `quit` / `退出` | 退出系统 |

## 交互示例

```
============================================================
       智能医疗诊断多Agent交互系统
============================================================

系统已就绪！输入问题开始对话，输入 'quit' 或 '退出' 结束。
------------------------------------------------------------

[用户] 你好

[助手] 您好！我是智能医疗助手，可以为您提供以下服务：
  1. 预约挂号 - 帮您预约医生门诊
  2. 排队叫号 - 管理您的就诊排队
  3. 医疗咨询 - 回答健康相关问题
  4. 症状诊断 - 根据症状提供初步分析
请问您需要什么帮助？

[用户] 我最近总是头疼，还伴随恶心

[助手] 您好，我是症状诊断助手。为了更好地分析您的情况，
       请问您的头疼持续多长时间了？
       ...
```

## 核心设计

### 多Agent协作

RouterAgent 接收所有用户输入，通过 LLM 输出结构化 JSON 进行意图分类，置信度低于 0.6 时自动追问澄清。分类结果路由至对应的专业 Agent 处理。

### RAG 检索管线

1. **查询改写：** LLM 将口语化表述改写为专业医学查询，提取关键词与同义扩展词
2. **多路检索：** 基于改写结果与关键词分别执行 ChromaDB 向量检索
3. **结果融合：** 按文档 ID 去重，保留最优距离分数，注入 LLM 上下文

### 工具调用

通过 Prompt Engineering 实现，系统提示词中嵌入工具 Schema，LLM 输出 JSON 格式的工具调用指令，代码端解析并执行后将结果反馈给 LLM 合成自然语言回复。不依赖原生 Function Calling API。

### LangChain 集成

LLM 调用和 Embedding 生成均通过 LangChain 框架封装：
- `ChatTongyi`（langchain-community）封装通义千问 qwen-plus，支持流式输出
- `DashScopeEmbeddings`（langchain-community）封装 text-embedding-v3 向量化
- 对话历史使用 LangChain 消息类型（SystemMessage、HumanMessage、AIMessage）
- 上层 Agent 逻辑与底层 LLM 解耦，便于切换模型或扩展能力

## 免责声明

本系统仅用于技术演示和学习目的，不构成任何医疗建议。如有健康问题，请务必咨询专业医疗机构。
