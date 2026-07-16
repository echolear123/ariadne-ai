"""共享类型定义 - 函数式架构的核心数据结构

本文件定义所有模块共享的数据类型和回调协议。
不包含任何 IO 或业务逻辑，可独立测试。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path


# ============================================================
# 回调/扩展协议
# ============================================================

# 调试回调: 每个模块的操作都会调用此回调，传递 (module, action, detail)
DebugCallback = Callable[[str, str, Any], None]

# 日志回调: 模块日志统一出口
LogCallback = Callable[[str, str, str], None]  # (action, level, detail_str)


# ============================================================
# 记忆相关
# ============================================================

@dataclass
class MemoryEntry:
    """记忆查询返回的标准条目"""
    content: str
    source: str          # 来源标识: corrections / faq / docs_index / zvec / skill
    priority: int        # 优先级，数字越小越高
    metadata: Dict = field(default_factory=dict)


# ============================================================
# 技能相关
# ============================================================

@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    triggers: List[str]          # 触发关键词
    sop_steps: List[str]         # 执行思维链步骤
    output_template: str         # 强制输出格式
    entity_refs: List[str] = field(default_factory=list)  # 依赖的实体文件
    metadata: Dict = field(default_factory=dict)


# ============================================================
# 向量库相关
# ============================================================

@dataclass
class ChunkSpec:
    """文档切片规格"""
    id: str
    text: str
    source: str
    chunk_index: int = 0


@dataclass
class SearchResult:
    """向量搜索返回"""
    content: str
    source: str
    score: float
    id: str
    chunk_index: int = 0


# ============================================================
# 路由/回答相关
# ============================================================

@dataclass
class RouteMeta:
    """路由元信息，含调试数据"""
    query: str
    skill: Optional[str] = None
    memory_sources: List[str] = field(default_factory=list)
    memory_count: int = 0
    debug: List[Dict] = field(default_factory=list)


@dataclass
class RouteResult:
    """路由结果"""
    answer: str
    meta: RouteMeta


# ============================================================
# 审查相关
# ============================================================

@dataclass
class ReviewResult:
    """问答审查结果"""
    scores: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    deposited: bool = False
    cluster: Optional[str] = None
    skipped: bool = False


# ============================================================
# 对话历史
# ============================================================

@dataclass
class ChatTurn:
    """单轮对话"""
    query: str
    answer: str
    timestamp: str = ""


# ============================================================
# 审计日志
# ============================================================

@dataclass
class AuditEntry:
    """一条审计记录"""
    timestamp: str
    action: str
    level: str
    detail: Dict


# ============================================================
# 配置类型
# ============================================================

@dataclass
class AgentConfig:
    """Agent 全局配置"""
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    embedding_model: str
    source_dir: Path
    fast_memory_dir: Path
    zvec_dir: Path
    audit_log_path: Path
    schema_file: Path
    index_file: Path
    corrections_file: Path
    public_faq_file: Path
    entities_dir: Path
    docs_index_dir: Path
    skills_dir: Path
    default_top_k: int = 5
    match_threshold: float = 0.3
