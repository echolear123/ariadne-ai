"""审计日志 - 函数式架构

工厂: create_audit_logger(log_path, *, on_debug=None, log=None)
返回 SimpleNamespace 含: log_action, query, _state
"""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, List, Dict

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 纯函数
# ============================================================

def log_action(state: dict, action: str, detail: Dict, level: str = "INFO") -> None:
    """追加一条审计记录"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "level": level,
        "detail": detail
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    with open(state["log_path"], "a", encoding="utf-8") as f:
        f.write(line)

    # 扩展/调试回调
    if state.get("_on_debug"):
        state["_on_debug"]("audit_logger", "log_action", {"action": action, "level": level})
    if state.get("_log"):
        state["_log"](action, level, json.dumps(detail, ensure_ascii=False))


def query_logs(state: dict, action: Optional[str] = None,
               start_time: Optional[str] = None,
               end_time: Optional[str] = None,
               limit: int = 100) -> List[Dict]:
    """查询审计日志"""
    log_path = state["log_path"]
    if not log_path.exists():
        return []

    results = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if action and entry.get("action") != action:
                continue
            if start_time and entry.get("timestamp", "") < start_time:
                continue
            if end_time and entry.get("timestamp", "") > end_time:
                continue

            results.append(entry)
            if len(results) >= limit:
                break
    return results


# ============================================================
# 工厂
# ============================================================

def create_audit_logger(log_path: Path, *,
                        on_debug: DebugCallback = None,
                        log: LogCallback = None) -> SimpleNamespace:
    """创建审计日志模块

    Args:
        log_path: 日志文件路径
        on_debug: 调试回调, 签名 (module, action, detail)
        log: 日志回调, 签名 (action, level, detail_str)

    Returns:
        SimpleNamespace with:
          - log_action(action, detail, level): 记录事件
          - query(action, start_time, end_time, limit): 查询日志
          - _state: 内部状态 (调试用)
    """
    state = {
        "log_path": Path(log_path),
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        log_action=lambda action, detail, level="INFO": log_action(state, action, detail, level),
        query=lambda action=None, start_time=None, end_time=None, limit=100:
            query_logs(state, action, start_time, end_time, limit),
        # 扩展/调试接口
        _state=state,
    )
