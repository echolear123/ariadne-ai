# Agent - 函数式接口层
# 所有模块通过共享类型和回调协议关联，实现松耦合的函数式架构
from interfaces.types import (
    DebugCallback, LogCallback,
    MemoryEntry, Skill, ChunkSpec, SearchResult,
    RouteMeta, RouteResult, ReviewResult,
    ChatTurn, AuditEntry, AgentConfig,
)
