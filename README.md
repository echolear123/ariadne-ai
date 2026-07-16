# Ariadne AI

> 循此红线，洞见万卷。

基于本地文档的智能知识库问答系统。支持 PDF/DOCX/MD 文档自动入库、向量检索、Markdown 画布、插件系统和多用户管理。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/React-19-61dafb" alt="React">
  <img src="https://img.shields.io/badge/ZVec-local-8b5cf6" alt="ZVec">
  <img src="https://img.shields.io/badge/LLM-Qwen3--8B-22c55e" alt="LLM">
</p>

---

## 功能特性

- **文档智能问答** — 上传 PDF/DOCX/TXT/MD 后自动入库，基于向量检索 + LLM 生成准确回答
- **知识库管理** — Web 端可视化管理文档：上传、下载、删除、备注；向量库条目查看与清理
- **Markdown 画布** — 拖拽卡片、贝塞尔连线、自由绘图标注；AI 画布助手直接对卡片内容提问
- **插件系统** — 可扩展的 MCP 协议插件（计算器、文档统计、画布总结等）
- **自进化知识库** — 自动聚类高频问答入 FAQ；管理员纠错覆盖；实体消歧
- **多用户认证** — 配置文件管理用户凭据；对话完全隔离
- **SSE 流式输出** — 实时 token 级流式渲染，支持 Markdown 表格/代码高亮

---

## 快速开始

### 1. 环境准备

```bash
git clone https://github.com/your-username/ariadne-ai.git
cd ariadne-ai
pip install -r requirements.txt
```

### 2. 配置 API Key

复制环境变量模板并填入你的 SiliconFlow API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
SF_API_KEY=sk-your-api-key-here
SF_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3-8B
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

> 注册 SiliconFlow：https://siliconflow.cn （免费额度足够日常使用）

### 3. 入库文档

将文档放入 `source/` 目录，执行：

```bash
python main.py index
```

### 4. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

### 5. 启动服务

```bash
python app.py
```

打开浏览器访问 `http://localhost:7860`，使用默认账号 `echo` / `echo123` 登录。

---

## 项目结构

```
ariadne-ai/
├── app.py                    # Flask Web 服务 (SSE 流式 + API)
├── config.py                 # 全局配置 (LLM/Embedding/路径)
├── main.py                   # CLI 入口 (交互/索引/管理)
├── doc_reader.py             # 文档读取器 (PDF/DOCX/MD 提取 + 切片)
├── core/                     # 核心编排层
│   ├── agent.py              # 主编排器工厂 (依赖注入)
│   ├── router.py             # 对话路由 (检索调度 / 查询重写 / 工具循环)
│   ├── context_builder.py    # LLM 上下文组装
│   ├── session.py            # 会话管理 (SQLite 持久化 / 摘要)
│   ├── reviewer.py           # 后台审查 (自进化 FAQ)
│   └── history.py            # 历史查阅工具
├── memory/                   # 双轨记忆层
│   ├── fast_memory.py        # 快记忆 (Markdown Wiki)
│   ├── long_memory.py        # 长记忆 (向量 + 关键词双路检索)
│   └── vector_store.py       # ZVec 向量库包装
├── fast_memory/              # 系统提示词 + 知识数据 (Wiki)
│   ├── schema.md             # 系统运作规范 (每轮注入 LLM)
│   ├── corrections.md        # 管理员纠错 (最高优先级)
│   ├── public_faq.md         # 自进化高频问答
│   ├── entities/             # 实体对齐字典
│   ├── docs_index/           # 文档骨架卡片
│   └── skills/               # SOP 技能定义
├── source/                   # 源文档目录
├── knowledge_base/           # 结构化知识库 (按来源递归组织)
├── plugins/                  # 插件系统 (calculator / canvas_md / doc_stats)
├── interfaces/               # 类型定义
├── audit/                    # 审计日志
├── static/                   # React 构建产物
└── frontend/                 # React 前端源码
    └── src/
        ├── pages/
        │   ├── Login.jsx          # 登录页 (macOS 动态背景)
        │   ├── Chat.jsx           # 聊天主界面
        │   ├── DocumentManager.jsx # 知识库管理
        │   └── CanvasPage.jsx     # Markdown 画布 (卡片 + 绘图)
        └── components/
            ├── Sidebar.jsx
            ├── MacPatternBackground.jsx
            └── PluginLibrary.jsx
```

---

## 架构

### 请求处理管道

```
用户查询
  │
  ├─ 1. 技能匹配          → skill_provider.match()
  ├─ 2. 实体消歧          → entities/*.md
  ├─ 3. LLM 查询重写      → 指代消解 ("这个文件" → 完整问题)
  ├─ 4. 双轨记忆检索       → fast_memory + ZVec 向量检索 (并行)
  ├─ 5. 上下文组装        → schema + 计划 + 历史 + 记忆 + 清单
  ├─ 6. LLM 流式生成      → Qwen3-8B (SSE 逐 token)
  ├─ 7. 工具循环 (≤3轮)   → [TOOL:read_pdf / recall_turn / update_plan]
  └─ 8. 记录持久化        → session.add_turn() → SQLite
```

### 双轨记忆

| 记忆层 | 存储 | 方法 |
|--------|------|------|
| **快记忆** | Markdown Wiki (corrections / faq) | 关键词精确匹配 |
| **长记忆** | ZVec 向量库 | bge-large-zh-v1.5 → 语义检索 |

### 工具指令

LLM 回答末尾可输出工具指令，系统自动执行后重新生成：

| 指令 | 作用 |
|------|------|
| `[TOOL:read_pdf:文件名:页-页]` | 提取 PDF 指定页面 |
| `[TOOL:recall_turn:N]` | 查阅第 N 轮对话原文 |
| `[TOOL:recall_range:M-N]` | 查阅区间对话原文 |
| `[TOOL:update_plan:JSON]` | 更新任务计划状态 |

---

## API 参考

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/login` | POST | 用户登录 |
| `/api/chat` | POST | SSE 流式问答 |
| `/api/upload-document` | POST | 上传文档自动入库 |
| `/api/documents` | GET | 文档列表 |
| `/api/document/<name>` | DELETE | 删除文档及向量 |
| `/api/document/<name>/download` | GET | 下载原始文件 |
| `/api/document/<name>/notes` | PUT | 更新文档备注 |
| `/api/vector-entries` | GET | 向量库条目列表 |
| `/api/vector-entry/<id>` | DELETE | 删除单条向量 |
| `/api/vector-stats` | GET | 向量库统计 |
| `/api/vector-optimize` | POST | 重建向量索引 |
| `/api/plugins` | GET | 插件列表 |
| `/api/conversations` | GET | 会话列表 |
| `/api/conversation/<id>` | GET | 会话详情 |
| `/api/canvases` | GET | 画布列表 |
| `/api/canvas/<id>` | GET/PUT/DELETE | 画布 CRUD |

---

## 配置参考

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `SF_API_KEY` | (必填) | SiliconFlow API 密钥 |
| `LLM_MODEL` | Qwen/Qwen3-8B | 对话模型 |
| `EMBEDDING_MODEL` | BAAI/bge-large-zh-v1.5 | 向量化模型 |
| `WEB_HOST` | 0.0.0.0 | 监听地址 |
| `WEB_PORT` | 7860 | 监听端口 |
| `DEFAULT_TOP_K` | 5 | 向量检索 TopK |
| `MATCH_THRESHOLD` | 0.3 | 关键词匹配阈值 |
| `SUMMARY_TRIGGER_TURNS` | 10 | 对话摘要触发轮数 |

在 `config.py` 中可进一步自定义路径、切片参数等。

---

## 管理

```bash
# 添加管理员纠错
python main.py correct "关键词" "修正内容"

# 热重载技能
python main.py reload-skills

# 查看审计日志
python main.py audit

# 重建索引
python main.py index
```

用户管理在 `config.py` 的 `USERS` 字典中：

```python
USERS = {
    "echo": "echo123",
    # 在此添加更多用户
}
```

---

## 技术栈

| 层 | 技术 |
|---|------|
| LLM | SiliconFlow API / Qwen3-8B |
| Embedding | bge-large-zh-v1.5 (1024 dim) |
| 向量库 | ZVec (Proxima ANN, 本地持久化) |
| 文档解析 | pypdf / python-docx |
| Web 框架 | Flask (SSE 流式) |
| 前端 | React 19 + Vite + react-markdown + remark-gfm |
| 对话存储 | SQLite (tech_bureau_sessions.db) |

---

## License

MIT License
