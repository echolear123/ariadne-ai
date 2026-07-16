"""长记忆层 - 函数式架构

向量语义 + 关键词双重检索。依赖 vector_store 模块。

工厂: create_long_memory(vector_store, *, on_debug=None, log=None)
返回 SimpleNamespace 含: query, rebuild, count, name, priority, _state
"""

from types import SimpleNamespace
import time
from typing import List, Dict, Set

from interfaces.types import MemoryEntry, DebugCallback, LogCallback


# ============================================================
# 状态操作函数
# ============================================================

def query_memory(state: dict, query: str, top_k: int = 5) -> List[MemoryEntry]:
    """向量检索 + 关键词检索，合并去重。卡片条目自动赋予 priority=3"""
    vector_store = state["vector_store"]
    seen: Set[str] = set()
    entries: List[MemoryEntry] = []

    # 1. 向量语义检索
    t0 = time.time()
    vec_results = vector_store.search(query, top_k=top_k)
    vec_ms = round((time.time() - t0) * 1000)
    print(f"    [LongMemory] vector search → {len(vec_results)} hits in {vec_ms}ms")

    for r in vec_results:
        rid = r["id"]
        if rid not in seen and r.get("content"):
            seen.add(rid)
            src = r.get("source", "")
            # docs_index 卡片: id 以 card_ 开头或 source 含 docs_index/
            is_card = rid.startswith("card_") or "docs_index" in src
            entries.append(MemoryEntry(
                content=r["content"],
                source=src,
                priority=3 if is_card else 10,
                metadata={"doc": src, "chunk": r.get("chunk_index", 0)}
            ))

    # 2. 关键词全文检索
    t1 = time.time()
    kw_results = vector_store.keyword_search(query, top_k=top_k)
    kw_ms = round((time.time() - t1) * 1000)
    print(f"    [LongMemory] keyword search → {len(kw_results)} hits in {kw_ms}ms")

    for r in kw_results:
        rid = r["id"]
        if rid not in seen and r.get("content"):
            seen.add(rid)
            src = r.get("source", "")
            is_card = rid.startswith("card_") or "docs_index" in src
            entries.append(MemoryEntry(
                content=r["content"],
                source=src,
                priority=3 if is_card else 12,
                metadata={"doc": src, "chunk": r.get("chunk_index", 0)}
            ))

    if state.get("_on_debug"):
        state["_on_debug"]("long_memory", "query",
                           {"query": query[:50], "vec_hits": len(vec_results),
                            "kw_hits": len(kw_results), "total": len(entries)})

    return entries[:top_k]


def rebuild_store(state: dict, all_chunks: List[Dict],
                  docs_index_cards: List[dict] = None) -> None:
    """清空并重建整个向量索引 (文档切片 + 可选 docs_index 卡片)"""
    vector_store = state["vector_store"]
    vector_store.rebuild()
    if all_chunks:
        vector_store.add_chunks(all_chunks)
    if docs_index_cards:
        vector_store.index_docs_index(docs_index_cards)

    if state.get("_on_debug"):
        state["_on_debug"]("long_memory", "rebuild",
                           {"chunks": len(all_chunks) if all_chunks else 0,
                            "cards": len(docs_index_cards) if docs_index_cards else 0})
    if state.get("_log"):
        state["_log"]("long_memory", "INFO",
                      f"rebuilt with {len(all_chunks) if all_chunks else 0} chunks"
                      + (f" + {len(docs_index_cards)} cards" if docs_index_cards else ""))


def count_docs(state: dict) -> int:
    return state["vector_store"].count()


# ============================================================
# 工厂
# ============================================================

def create_long_memory(vector_store, *,
                       on_debug: DebugCallback = None,
                       log: LogCallback = None) -> SimpleNamespace:
    """创建长记忆模块

    Args:
        vector_store: create_vector_store 返回的向量存储模块
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - query(query, top_k) -> List[MemoryEntry]: 混合检索
          - rebuild(all_chunks, docs_index_cards=None): 全量重建 (可选卡片)
          - count() -> int: 记录数
          - vector_store: 底层向量库 (可直接访问)
          - name: "LongMemory"
          - priority: 10
          - _state: 内部状态 (调试用)
    """
    state = {
        "vector_store": vector_store,
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        query=lambda q, top_k=5: query_memory(state, q, top_k),
        rebuild=lambda chunks, cards=None: rebuild_store(state, chunks, cards),
        count=lambda: count_docs(state),
        vector_store=vector_store,
        name="LongMemory",
        priority=10,
        # 扩展/调试接口
        _state=state,
    )
