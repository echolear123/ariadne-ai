"""对话历史管理 - 函数式架构

工厂: create_chat_history(max_turns=10, max_chars=3000, *, on_debug=None, log=None)
返回 SimpleNamespace 含: add, get_context, clear, _state
"""

from datetime import datetime
from types import SimpleNamespace
from typing import List, Dict

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 纯函数
# ============================================================

def add_turn(state: dict, query: str, answer: str) -> None:
    """添加一轮对话"""
    state["_history"].append({
        "q": query,
        "a": answer[:500],
        "ts": datetime.now().strftime("%H:%M")
    })
    while len(state["_history"]) > state["max_turns"]:
        state["_history"].pop(0)

    if state.get("_on_debug"):
        state["_on_debug"]("chat_history", "add", {"turns": len(state["_history"])})


def get_context(state: dict) -> str:
    """生成最近对话摘要上下文"""
    history = state["_history"]
    if not history:
        return ""

    max_chars = state["max_chars"]
    trimmed = []
    total = 0
    for h in reversed(history):
        add_chars = len(h["q"]) + len(h["a"])
        if total + add_chars > max_chars:
            break
        trimmed.insert(0, h)
        total += add_chars

    if not trimmed:
        return ""

    lines = ["【最近对话历史 - 请基于此前对话理解用户的指代和上下文】"]
    for h in trimmed:
        lines.append(f"用户[{h['ts']}]: {h['q']}")
        lines.append(f"助手[{h['ts']}]: {h['a'][:200]}")
        lines.append("")
    return "\n".join(lines)


def clear_history(state: dict) -> None:
    state["_history"].clear()
    if state.get("_on_debug"):
        state["_on_debug"]("chat_history", "clear", {})


# ============================================================
# 工厂
# ============================================================

def create_chat_history(max_turns: int = 10, max_chars: int = 3000, *,
                        on_debug: DebugCallback = None,
                        log: LogCallback = None) -> SimpleNamespace:
    """创建对话历史模块

    Args:
        max_turns: 最多保留轮数
        max_chars: 历史最大总字符数
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - add(query, answer): 添加一轮
          - get_context() -> str: 获取上下文字符串
          - clear(): 清空历史
          - _state: 内部状态 (调试用)
    """
    state = {
        "_history": [],
        "max_turns": max_turns,
        "max_chars": max_chars,
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        add=lambda q, a: add_turn(state, q, a),
        get_context=lambda: get_context(state),
        clear=lambda: clear_history(state),
        # 扩展/调试接口
        _state=state,
    )
