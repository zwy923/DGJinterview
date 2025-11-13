# 大狗叫面试助手

一个基于 AI 的智能面试助手系统，提供实时语音识别、智能问答生成、RAG 检索等功能，帮助求职者更好地准备和应对面试。

## ✨ 核心功能

### 🎤 实时语音识别（ASR）
- **双音频源支持**：支持麦克风输入和系统音频捕获
- **实时流式识别**：基于 FunASR 的实时语音转文字
- **智能端点检测**：VAD（Voice Activity Detection）自动检测语音开始和结束
- **音频去噪**：支持高频滤波、谱减法和噪声门控
- **后处理优化**：口语清理、标点修正、数字规范化、重复词过滤

### 🤖 AI 智能问答
- **RAG 增强检索**：
  - CV 向量检索（整体 embedding）
  - JD 关键词匹配
  - 外部知识库向量检索
- **流式回答生成**：支持 SSE（Server-Sent Events）实时流式输出
- **上下文感知**：结合对话历史、CV、JD 和知识库生成个性化回答
- **多模型支持**：支持 GPT-4o-mini、GPT-5-mini 等多种 LLM 模型

### 📚 知识库管理
- **自动向量化**：添加知识库条目时自动生成 embedding
- **向量检索**：基于 pgvector 的高效相似度搜索
- **Session 隔离**：支持按面试会话隔离知识库内容

### 📄 CV 和 JD 管理
- **CV 管理**：上传和管理个人简历，支持自动 embedding 生成
- **JD 管理**：管理岗位描述和职位要求
- **智能匹配**：基于向量相似度匹配 CV 和 JD

### 💬 对话历史
- **完整记录**：记录面试官问题和用户回答
- **历史检索**：支持基于 embedding 的对话历史检索
- **统计分析**：提供对话统计和分析功能

## 🏗️ 技术架构

### 后端技术栈
- **Web 框架**：FastAPI
- **ASR 引擎**：FunASR（Paraformer + VAD + 标点模型）
- **数据库**：PostgreSQL + pgvector（向量数据库）
- **LLM 服务**：OpenAI API（支持自定义 base URL）
- **实时通信**：WebSocket（音频流）、SSE（流式回答）
- **音频处理**：PyAudio、SoundFile、NumPy

### 前端技术栈
- **框架**：React 19 + TypeScript
- **构建工具**：Vite
- **路由**：React Router
- **音频处理**：Web Audio API、AudioWorklet

### 系统架构

```
┌─────────────────┐
│   React 前端     │
│  (TypeScript)    │
└────────┬────────┘
         │ HTTP/WebSocket/SSE
         ▼
┌─────────────────┐
│   FastAPI 后端   │
│                 │
│  ┌───────────┐  │
│  │ ASR Pipeline│ │
│  │ (FunASR)  │  │
│  └───────────┘  │
│                 │
│  ┌───────────┐  │
│  │ RAG Service│ │
│  │ (Vector)  │  │
│  └───────────┘  │
│                 │
│  ┌───────────┐  │
│  │ LLM Service│ │
│  │ (OpenAI)  │  │
│  └───────────┘  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PostgreSQL     │
│  + pgvector     │
└─────────────────┘
```

## 🚀 快速开始

### 环境要求

- **Python**: 3.12+
- **Node.js**: 18+
- **PostgreSQL**: 14+（需安装 pgvector 扩展）
- **CUDA**（可选）：用于 GPU 加速 ASR（CPU 模式也可运行）

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/zwy923/DGJinterview.git
cd intervew
```

#### 2. 后端设置

```bash
# 进入 server 目录
cd server

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 3. 数据库设置

```bash
# 创建数据库
createdb interview

# 连接到数据库并安装 pgvector 扩展
psql interview
CREATE EXTENSION vector;
```

#### 4. 环境变量配置

在 `server` 目录下创建 `.env` 文件：

```env
# 应用配置
DEBUG=false
HOST=0.0.0.0
PORT=8000

# PostgreSQL 配置
PG_HOST=localhost
PG_PORT=5432
PG_DB=interview
PG_USER=postgres
PG_PASSWORD=your_password
PG_ENABLED=true

# ASR 配置
ASR_DEVICE=cuda  # 或 cpu
ASR_ENABLE_DENOISE=true
ASR_MIN_SENTENCE_LENGTH=8

# LLM 配置
LLM_API_KEY=your_openai_api_key
LLM_BASE_URL=https://api.openai.com/v1
MODEL_NAME_BRIEF=gpt-4o-mini
MODEL_NAME_FULL=gpt-4o-mini
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# Embedding 配置
EMBEDDING_API_KEY=your_openai_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# RAG 配置
RAG_TOPK=5
RAG_TOKEN_BUDGET=1200
CHAT_HISTORY_MAX=50
```

#### 5. 前端设置

```bash
# 进入 client 目录
cd client

# 安装依赖
npm install
```

#### 6. 启动服务

**启动后端**（在 `server` 目录）：

```bash
python main.py
# 或
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**启动前端**（在 `client` 目录）：

```bash
npm run dev
```

访问 `http://localhost:5173` 即可使用系统。

## 📖 使用指南

### 1. 创建面试会话

1. 在首页点击"新建面试"
2. 填写面试信息：
   - 岗位名称
   - 岗位要求
   - 编程语言（可选）
3. 点击"开始面试"

### 2. 管理 CV

1. 在首页点击"管理简历"
2. 上传或编辑简历内容
3. 系统会自动生成 embedding 用于向量检索

### 3. 管理知识库

1. 在首页或面试页面点击"知识库管理"
2. 添加知识库条目（标题和内容）
3. 系统会自动生成 embedding 用于检索

### 4. 使用语音识别

1. 在面试页面点击麦克风按钮开始录音
2. 系统会实时识别语音并显示文字
3. 支持麦克风和系统音频两种输入源

### 5. 获取 AI 回答建议

1. 选择面试官的问题（可多选）
2. 点击"回答"按钮
3. AI 会基于 CV、JD、知识库和对话历史生成回答建议
4. 回答会以流式方式实时显示

## 🔧 配置说明

### ASR 配置

- `ASR_DEVICE`: 设备类型（`cuda` 或 `cpu`）
- `ASR_ENABLE_DENOISE`: 是否启用音频去噪
- `ASR_MIN_SENTENCE_LENGTH`: 最小句子长度（字符数）
- `VAD_PRE_SPEECH_PADDING`: 前置缓冲时间（秒）
- `VAD_END_SILENCE`: 尾静音时间（秒）
- `VAD_MAX_SEGMENT`: 最大段长（秒）

### RAG 配置

- `RAG_TOPK`: 外部知识库检索 top-k
- `RAG_TOKEN_BUDGET`: RAG token 预算
- `CHAT_HISTORY_MAX`: 对话历史最大条数

### LLM 配置

- `MODEL_NAME_BRIEF`: 快答模式模型名
- `MODEL_NAME_FULL`: 正常模式模型名
- `LLM_TEMPERATURE`: 温度参数
- `LLM_MAX_TOKENS`: 最大 token 数

## 📁 项目结构

```
intervew/
├── server/                 # 后端服务
│   ├── agents/            # AI Agent
│   │   └── answer_agent.py # 回答生成 Agent
│   ├── api/               # API 端点
│   │   └── gpt_endpoints.py # GPT 相关端点
│   ├── asr/               # 语音识别模块
│   │   ├── engine.py      # ASR 引擎
│   │   ├── pipeline.py    # ASR 处理管道
│   │   ├── postprocess.py # 后处理
│   │   └── session.py     # 会话管理
│   ├── core/              # 核心模块
│   │   ├── config.py      # Agent 配置
│   │   ├── state.py       # 会话状态
│   │   └── types.py       # 类型定义
│   ├── gateway/           # WebSocket 网关
│   │   └── ws_audio.py    # 音频 WebSocket
│   ├── services/          # 业务服务
│   │   ├── doc_store.py  # 文档存储服务
│   │   ├── embed_service.py # Embedding 服务
│   │   ├── llm_service.py   # LLM 服务
│   │   └── rag_service.py   # RAG 检索服务
│   ├── storage/           # 数据存储
│   │   ├── dao.py         # 数据访问对象
│   │   └── pg.py          # PostgreSQL 连接池
│   ├── utils/             # 工具函数
│   │   ├── audio.py       # 音频处理工具
│   │   ├── sse.py         # SSE 工具
│   │   └── schemas.py     # 数据模型
│   ├── ws/                # WebSocket 处理
│   │   ├── ws_agent.py    # Agent WebSocket
│   │   └── ws_audio.py    # 音频 WebSocket
│   ├── api_routes.py      # API 路由
│   ├── config.py          # 应用配置
│   ├── main.py            # 应用入口
│   └── requirements.txt   # Python 依赖
│
├── client/                # 前端应用
│   ├── src/
│   │   ├── api/           # API 客户端
│   │   ├── audio/         # 音频处理
│   │   ├── components/    # React 组件
│   │   │   ├── AudioController.tsx    # 音频控制器
│   │   │   ├── CVManager.tsx          # CV 管理
│   │   │   ├── HomePage.tsx          # 首页
│   │   │   ├── InterviewPage.tsx     # 面试页面
│   │   │   ├── KnowledgeBaseManager.tsx # 知识库管理
│   │   │   ├── LeftPanel.tsx         # 左侧面板（对话）
│   │   │   └── RightPanel.tsx        # 右侧面板（AI 回答）
│   │   └── styles/        # 样式文件
│   ├── package.json       # Node.js 依赖
│   └── vite.config.ts     # Vite 配置
│
└── README.md              # 项目说明文档
```

## 🔍 核心特性详解

### RAG 检索策略

1. **CV 检索**：使用向量相似度检索（整体 embedding）
2. **JD 检索**：使用关键词提取和匹配
3. **知识库检索**：使用向量相似度检索
4. **智能融合**：根据 token 预算智能裁剪和融合检索结果

### 流式输出机制

- **后端**：使用 `asyncio.Queue` 实现真正的实时流式输出
- **前端**：使用 `fetch` API 和 `TextDecoder` 处理 SSE 流
- **降级处理**：对于不支持流式的模型，自动降级为模拟流式输出

### 音频处理流程

1. **音频采集**：Web Audio API → AudioWorklet → WebSocket
2. **VAD 检测**：检测语音开始和结束
3. **ASR 识别**：FunASR 实时识别
4. **后处理**：去噪、清理、规范化
5. **结果输出**：实时显示识别结果

## 🐛 故障排除

### ASR 识别卡死

- 检查 `ASR_DEVICE` 配置是否正确
- 增加 `ThreadPoolExecutor` 的 `max_workers`
- 检查音频输入设备是否正常

### 数据库连接失败

- 确认 PostgreSQL 服务正在运行
- 检查 `.env` 中的数据库配置
- 确认 pgvector 扩展已安装

### Embedding 生成失败

- 检查 `EMBEDDING_API_KEY` 是否正确
- 确认网络连接正常
- 查看日志了解详细错误信息

## 📝 开发说明

### 添加新的 LLM 模型支持

在 `server/services/llm_service.py` 中：

1. 添加模型检测逻辑（如需要特殊参数）
2. 实现参数适配（如 `max_tokens` vs `max_completion_tokens`）
3. 处理流式输出兼容性

### 自定义 ASR 后处理

在 `server/asr/postprocess.py` 中：

1. 添加新的清理规则
2. 调整过滤阈值
3. 实现自定义规范化逻辑

### 扩展 RAG 检索

在 `server/services/rag_service.py` 中：

1. 添加新的检索源
2. 实现自定义检索策略
3. 优化 token 预算分配

## 📄 许可证

查看 [LICENSE](LICENSE) 文件了解详情。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题或建议，请通过 Issue 联系。

---

**注意**：本项目需要 OpenAI API Key 才能使用 LLM 和 Embedding 功能。请确保在 `.env` 文件中正确配置了 API Key。

