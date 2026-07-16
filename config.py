"""全局配置 - 修改路径即可切换数据源，无需改动代码"""

import os
from pathlib import Path

# 自动加载 .env 文件
_ENV_PATH = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# === LLM API (硅基流动 / SiliconFlow) ===
# 优先从环境变量读取，支持 .env 文件
LLM_API_KEY = os.environ.get("SF_API_KEY", "your-api-key")
LLM_BASE_URL = os.environ.get("SF_BASE_URL", "https://api.siliconflow.cn/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")

# === 数据源层 (不可变只读区) ===
SOURCE_DIR = BASE_DIR / "source"
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"   # 结构化知识库 (按部门递归)

# === 双轨记忆层 ===
FAST_MEMORY_DIR = BASE_DIR / "fast_memory"      # 快记忆 Wiki 库
ZVEC_DIR = BASE_DIR / "tech_bureau_zvec"         # ZVec 向量库持久化目录

# === 审计 ===
AUDIT_LOG_PATH = BASE_DIR / "audit.log"

# === 快记忆关键文件 ===
SCHEMA_FILE       = FAST_MEMORY_DIR / "schema.md"
INDEX_FILE        = FAST_MEMORY_DIR / "index.md"
CORRECTIONS_FILE  = FAST_MEMORY_DIR / "corrections.md"
PUBLIC_FAQ_FILE   = FAST_MEMORY_DIR / "public_faq.md"
ENTITIES_DIR      = FAST_MEMORY_DIR / "entities"
DOCS_INDEX_DIR    = FAST_MEMORY_DIR / "docs_index"
SKILLS_DIR        = FAST_MEMORY_DIR / "skills"

# === 插件 (MCP 协议) ===
PLUGINS_DIR       = BASE_DIR / "plugins"

# === 检索参数 ===
DEFAULT_TOP_K = 5
MATCH_THRESHOLD = 0.3

# === 会话管理 ===
SESSIONS_DIR = FAST_MEMORY_DIR / "sessions"       # 对话持久化目录 (保留兼容)
SESSIONS_DB = BASE_DIR / "tech_bureau_sessions.db" # SQLite 会话数据库

# === 摘要参数 ===
SUMMARY_WINDOW_K = 5        # 最近 K 轮保留原文，之前的生成摘要
SUMMARY_TRIGGER_TURNS = 10  # 达到此轮数触发摘要
SUMMARY_TRIGGER_CHARS = 20000  # 达到此总字符数触发摘要
SUMMARY_TRIGGER_MINUTES = 30  # 最旧轮次超过此时间触发摘要

# === 用户认证 ===
# 用户名 → 密码，在此处添加/修改用户
USERS = {
    "echo": "echo123",
}

# === Web 服务 ===
WEB_HOST = "0.0.0.0"
WEB_PORT = 7860
