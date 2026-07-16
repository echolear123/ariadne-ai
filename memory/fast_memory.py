"""快记忆层 - 函数式架构

基于 Markdown Wiki 文件的高密度结构化知识库:
- schema.md: 顶层系统指令
- corrections.md: 最高优先级纠错覆盖 (Top-1)
- public_faq.md: 自进化高频问答库
- docs_index/: 文档宏观骨架卡片
- entities/: 实体对齐字典

工厂: create_fast_memory(base_dir, *, on_debug=None, log=None)
返回 SimpleNamespace 含: query, add_correction, add_faq, read_schema, read_index, read_entity_file, name, priority, _state
"""

import re
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Optional

from interfaces.types import MemoryEntry, DebugCallback, LogCallback


# ============================================================
# 纯函数 - 匹配工具
# ============================================================

def _text_match(query: str, text: str) -> bool:
    """文本匹配: 提取有意义中文词, 至少 2 个命中即匹配"""
    q = query.strip()
    if not q:
        return False
    if q in text:
        return True

    q_words = set()
    for n in (2, 3):
        for i in range(len(q) - n + 1):
            seg = q[i:i + n]
            if any('\u4e00' <= c <= '\u9fff' for c in seg):
                q_words.add(seg)

    if not q_words:
        return any(w in text for w in q.split() if len(w) > 1)

    hits = sum(1 for w in q_words if w in text)
    return hits >= 2 or (hits / len(q_words) >= 0.3)


def _keyword_match(keyword: str, query: str) -> bool:
    """模糊关键词匹配: 去除虚词后按字符重叠率匹配"""
    stop_chars = set("的了吗呢着之与和及或")
    kw_clean = "".join(c for c in keyword if c not in stop_chars)
    q_clean = "".join(c for c in query if c not in stop_chars)
    if not kw_clean:
        return keyword in query
    if kw_clean in q_clean:
        return True
    overlap = len(set(kw_clean) & set(q_clean))
    return overlap / len(set(kw_clean)) >= 0.7


# ============================================================
# 纯函数 - 解析
# ============================================================

def _parse_corrections(content: str) -> List[tuple]:
    """解析 corrections.md: ## [xxx] 格式"""
    entries = []
    pattern = r'##\s*\[(.+?)\]\s*\n+(.+?)(?=\n##\s*\[|\Z)'
    for m in re.finditer(pattern, content, re.DOTALL):
        keyword = m.group(1).strip()
        text = m.group(2).strip()
        entries.append((keyword, text))
    return entries


def _parse_faq(content: str) -> List[tuple]:
    """解析 FAQ: ## Q: ... ## A: ... 格式"""
    pairs = []
    pattern = r'##\s*Q:\s*(.+?)\n(.*?)(?=\n##\s*Q:|\n##\s*\[|\Z)'
    for m in re.finditer(pattern, content, re.DOTALL):
        q = m.group(1).strip()
        block = m.group(2).strip()
        block = re.sub(r'<!--.*?-->', '', block).strip()
        a_match = re.search(r'##\s*A:\s*\n+(.*?)$', block, re.DOTALL)
        a = a_match.group(1).strip() if a_match else block
        pairs.append((q, a))
    return pairs


# ============================================================
# 子检索函数 (纯函数)
# ============================================================

def _search_corrections(base_dir: Path, query: str) -> List[MemoryEntry]:
    """检索纠错库"""
    corrections_file = base_dir / "corrections.md"
    if not corrections_file.exists():
        return []

    content = corrections_file.read_text(encoding="utf-8")
    entries = _parse_corrections(content)
    matched = []

    for kw, text in entries:
        if _keyword_match(kw, query):
            matched.append(MemoryEntry(
                content=text,
                source="corrections",
                priority=1
            ))
    return matched


def _search_faq(base_dir: Path, query: str) -> List[MemoryEntry]:
    """模糊匹配 FAQ 库"""
    faq_file = base_dir / "public_faq.md"
    if not faq_file.exists():
        return []

    content = faq_file.read_text(encoding="utf-8")
    qa_pairs = _parse_faq(content)
    matched = []

    for q, a in qa_pairs:
        q_words = set(q)
        query_words = set(query)
        overlap = len(q_words & query_words) / max(len(q_words), 1)
        if overlap > 0.3:
            matched.append(MemoryEntry(
                content=f"Q: {q}\nA: {a}",
                source="public_faq",
                priority=2
            ))
    return matched


def _search_docs_index(base_dir: Path, query: str) -> List[MemoryEntry]:
    """搜索文档骨架卡片"""
    docs_dir = base_dir / "docs_index"
    if not docs_dir.exists():
        return []

    results = []
    for md_file in docs_dir.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        clean_name = re.sub(r'\.(pdf|docx|txt|md)$', '', md_file.name, flags=re.IGNORECASE)
        name_hit = _text_match(query, clean_name)
        content_hit = _text_match(query, content)

        if name_hit or content_hit:
            # 只取前 300 字符的卡片摘要，避免噪音淹没关键条目
            results.append(MemoryEntry(
                content=content[:300],
                source=f"docs_index/{md_file.name}",
                priority=3,
                metadata={"file": str(md_file),
                          "match_type": "name" if name_hit else "content"}
            ))
    return results


# ============================================================
# 状态操作函数
# ============================================================

import time as _time_mod

def query_memory(state: dict, query: str, top_k: int = 10) -> List[MemoryEntry]:
    """按优先级链检索: corrections > faq (docs_index 已移入 ZVec 向量检索)"""
    base_dir = state["base_dir"]
    results: List[MemoryEntry] = []

    t0 = _time_mod.time()
    results.extend(_search_corrections(base_dir, query))
    print(f"    [FastMemory] corrections → {len(results)} hits in {round((_time_mod.time() - t0) * 1000)}ms")

    pre = len(results)
    t1 = _time_mod.time()
    results.extend(_search_faq(base_dir, query))
    print(f"    [FastMemory] faq → +{len(results) - pre} hits in {round((_time_mod.time() - t1) * 1000)}ms")

    if state.get("_on_debug"):
        state["_on_debug"]("fast_memory", "query",
                           {"query": query[:50], "results": len(results)})

    return results[:top_k]


def get_docs_index_cards(base_dir: Path) -> List[dict]:
    """收集所有 docs_index 卡片，返回可在 ZVec 索引的 chunk 列表"""
    docs_dir = Path(base_dir) / "docs_index"
    if not docs_dir.exists():
        return []
    import hashlib
    cards = []
    for md_file in sorted(docs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")[:400]
        # 用 MD5 前 16 位作为安全 id
        card_id = "card_" + hashlib.md5(md_file.name.encode()).hexdigest()[:16]
        cards.append({
            "id": card_id,
            "text": content,
            "source": f"docs_index/{md_file.name}",
        })
    return cards


def add_correction(state: dict, keyword: str, corrected_content: str) -> None:
    """管理员提交修正条目"""
    corrections_file = state["base_dir"] / "corrections.md"
    entry = f"\n## [{keyword}]\n{corrected_content}\n"
    with open(corrections_file, "a", encoding="utf-8") as f:
        f.write(entry)

    if state.get("_on_debug"):
        state["_on_debug"]("fast_memory", "add_correction", {"keyword": keyword})
    if state.get("_log"):
        state["_log"]("correction", "INFO", f"added: [{keyword}]")


def add_faq_entry(state: dict, question: str, answer: str) -> None:
    """沉淀高频问答"""
    faq_file = state["base_dir"] / "public_faq.md"
    entry = f"\n## Q: {question}\n\n## A:\n{answer}\n"
    with open(faq_file, "a", encoding="utf-8") as f:
        f.write(entry)


def read_schema(state: dict) -> str:
    schema_file = state["base_dir"] / "schema.md"
    if schema_file.exists():
        return schema_file.read_text(encoding="utf-8")
    return ""


def read_index(state: dict) -> str:
    index_file = state["base_dir"] / "index.md"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return ""


def read_entity_file(state: dict, name: str) -> str:
    entity_file = state["base_dir"] / "entities" / f"{name}.md"
    if entity_file.exists():
        return entity_file.read_text(encoding="utf-8")
    return ""


# ============================================================
# 工厂
# ============================================================

def create_fast_memory(base_dir: Path, *,
                       on_debug: DebugCallback = None,
                       log: LogCallback = None) -> SimpleNamespace:
    """创建快记忆模块

    Args:
        base_dir: fast_memory 目录路径
        on_debug: 调试回调 (module, action, detail)
        log: 日志回调 (action, level, detail_str)

    Returns:
        SimpleNamespace with:
          - query(query, top_k) -> List[MemoryEntry]: 检索
          - add_correction(keyword, content): 添加纠错
          - add_faq(question, answer): 添加FAQ
          - read_schema() -> str: 读取系统指令
          - read_index() -> str: 读取知识图谱
          - read_entity_file(name) -> str: 读取实体
          - name: "FastMemory"
          - priority: 0
          - _state: 内部状态 (调试用)
    """
    state = {
        "base_dir": Path(base_dir),
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        query=lambda q, top_k=5: query_memory(state, q, top_k),
        add_correction=lambda kw, content: add_correction(state, kw, content),
        add_faq=lambda q, a: add_faq_entry(state, q, a),
        read_schema=lambda: read_schema(state),
        read_index=lambda: read_index(state),
        read_entity_file=lambda name: read_entity_file(state, name),
        get_docs_index_cards=lambda: get_docs_index_cards(state["base_dir"]),
        name="FastMemory",
        priority=0,
        # 扩展/调试接口
        _state=state,
    )
