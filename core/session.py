"""会话管理器 - SQLite 嵌入式数据库

管理对话生命周期: conversation_id / user_id / turn_id 持久化、
旧轮次摘要生成、任务计划缓冲区、历史查阅工具。

存储: SQLite (tech_bureau_sessions.db)，替代 JSON 文件系统。

工厂: create_session_manager(db_path, llm_client, llm_model, *, on_debug, log)
返回 SimpleNamespace 含: start, add_turn, get_context, recall_turn, update_plan, get_plan,
                     list_conversations, get_conversation, delete_conversation, _state
"""

import json
import re as _re
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Dict, Tuple, Any

import config


# ============================================================
# SQLite Schema
# ============================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    turn_counter INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn_range_start INTEGER NOT NULL,
    turn_range_end INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    key_topics TEXT NOT NULL DEFAULT '[]',
    key_entities TEXT NOT NULL DEFAULT '[]',
    key_decisions TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

CREATE TABLE IF NOT EXISTS plans (
    conversation_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_convs_user ON conversations(user_id, updated_at DESC);
"""


# ============================================================
# 数据库连接管理 (线程安全)
# ============================================================

_local = threading.local()


def _get_conn(db_path: str) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(db_path)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def _init_db(db_path: str) -> None:
    conn = _get_conn(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ============================================================
# 会话生命周期
# ============================================================

def start_conversation(state: dict, user_id: str = "default",
                       conversation_id: Optional[str] = None,
                       force_new: bool = False) -> dict:
    """创建或恢复一个会话，返回会话元信息"""
    conn = _get_conn(state["db_path"])

    if force_new:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        conversation_id = f"conv_{ts}"
    elif conversation_id is None:
        active = state.get("_active_conv")
        if active and active.get("user_id") == user_id:
            conversation_id = active["conversation_id"]
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            conversation_id = f"conv_{ts}"

    # 查询现有会话
    row = conn.execute(
        "SELECT conversation_id, user_id, turn_counter, created_at FROM conversations WHERE conversation_id = ?",
        (conversation_id,)
    ).fetchone()

    if row:
        state["_active_conv"] = {
            "user_id": row["user_id"],
            "conversation_id": row["conversation_id"],
        }
        return {
            "new": False, "user_id": row["user_id"],
            "conversation_id": row["conversation_id"],
            "turn_count": row["turn_counter"]
        }

    # 新建
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO conversations (conversation_id, user_id, created_at, updated_at, turn_counter) VALUES (?, ?, ?, ?, 0)",
        (conversation_id, user_id, now, now)
    )
    conn.commit()

    state["_active_conv"] = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }
    return {"new": True, "user_id": user_id, "conversation_id": conversation_id, "turn_count": 0}


def add_turn_op(state: dict, query: str, answer: str,
                meta: Optional[dict] = None) -> int:
    """追加一轮对话并持久化，返回 turn_id"""
    active = state.get("_active_conv")
    if not active:
        return -1

    conn = _get_conn(state["db_path"])
    cid = active["conversation_id"]

    # 更新计数器
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE conversations SET turn_counter = turn_counter + 1, updated_at = ? WHERE conversation_id = ?",
        (now, cid)
    )
    cur = conn.execute("SELECT turn_counter FROM conversations WHERE conversation_id = ?", (cid,))
    turn_id = cur.fetchone()["turn_counter"]

    # 写入 turn
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    conn.execute(
        "INSERT INTO turns (conversation_id, turn_id, timestamp, query, answer, meta) VALUES (?, ?, ?, ?, ?, ?)",
        (cid, turn_id, now, query, answer, meta_json)
    )
    conn.commit()

    # 异步检查是否需要生成摘要
    _maybe_trigger_summary(state)

    return turn_id


# ============================================================
# 摘要管理
# ============================================================

def _maybe_trigger_summary(state: dict) -> None:
    """检查是否满足摘要触发条件，异步执行"""
    active = state.get("_active_conv")
    if not active:
        return

    conn = _get_conn(state["db_path"])
    cid = active["conversation_id"]

    turns = conn.execute(
        "SELECT turn_id, query, answer, timestamp FROM turns WHERE conversation_id = ? ORDER BY turn_id",
        (cid,)
    ).fetchall()

    if not turns:
        return

    total_chars = sum(len(t["query"] or "") + len(t["answer"] or "") for t in turns)

    # 已摘要的轮次
    last_summarized = 0
    sum_rows = conn.execute(
        "SELECT MAX(turn_range_end) as max_end FROM summaries WHERE conversation_id = ?",
        (cid,)
    ).fetchone()
    if sum_rows and sum_rows["max_end"]:
        last_summarized = sum_rows["max_end"]

    unsummarized = [t for t in turns if t["turn_id"] > last_summarized]
    unsummarized_chars = sum(len(t["query"] or "") + len(t["answer"] or "") for t in unsummarized)

    triggered = (
        len(turns) >= config.SUMMARY_TRIGGER_TURNS
        or total_chars >= config.SUMMARY_TRIGGER_CHARS
        or _oldest_more_than_minutes(turns, config.SUMMARY_TRIGGER_MINUTES)
    )

    if not triggered:
        return

    k = config.SUMMARY_WINDOW_K
    summary_end = max(last_summarized, len(turns) - k)
    if summary_end <= last_summarized:
        return

    to_summarize = [t for t in turns if last_summarized < t["turn_id"] <= summary_end]
    if len(to_summarize) < 2:
        return

    _generate_summary(state, to_summarize, last_summarized + 1, summary_end)


def _oldest_more_than_minutes(turns, minutes: int) -> bool:
    if not turns:
        return False
    try:
        ts = datetime.fromisoformat(turns[0]["timestamp"])
        return (datetime.now() - ts) > timedelta(minutes=minutes)
    except (ValueError, KeyError):
        return False


def _generate_summary(state: dict, turns, start_id: int, end_id: int) -> None:
    """调用 LLM 为指定区间生成结构化摘要"""
    llm_client = state.get("llm_client")
    llm_model = state.get("llm_model")
    if not llm_client or len(turns) < 2:
        return

    dialogue = []
    for t in turns:
        dialogue.append(f"[轮次{t['turn_id']}] 用户: {t.get('query', '')[:500]}")
        dialogue.append(f"[轮次{t['turn_id']}] 助手: {t.get('answer', '')[:500]}")

    prompt = (
        "请为以下多轮对话生成一份结构化摘要，只返回 JSON，不要其他内容:\n\n"
        + "\n".join(dialogue) + "\n\n"
        '返回格式: {"summary": "涵盖所有关键主题、结论和决策的200字以内摘要", '
        '"key_topics": ["主题1","主题2"], '
        '"key_entities": ["实体1","实体2"], '
        '"key_decisions": ["决策1","决策2"]}'
    )

    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=300
        )
        text = resp.choices[0].message.content.strip()

        json_match = _re.search(r'\{[\s\S]*\}', text)
        summary_data = {}
        if json_match:
            summary_data = json.loads(json_match.group())

        now = datetime.now().isoformat()
        active = state.get("_active_conv")
        if active:
            conn = _get_conn(state["db_path"])
            conn.execute(
                "INSERT INTO summaries (conversation_id, turn_range_start, turn_range_end, generated_at, summary, key_topics, key_entities, key_decisions) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    active["conversation_id"], start_id, end_id, now,
                    summary_data.get("summary", text[:200]),
                    json.dumps(summary_data.get("key_topics", []), ensure_ascii=False),
                    json.dumps(summary_data.get("key_entities", []), ensure_ascii=False),
                    json.dumps(summary_data.get("key_decisions", []), ensure_ascii=False),
                )
            )
            conn.commit()

        if state.get("_on_debug"):
            state["_on_debug"]("session", "summary_generated",
                               {"range": [start_id, end_id], "topics": summary_data.get("key_topics", [])})
    except Exception:
        pass


# ============================================================
# 上下文组装
# ============================================================

def get_context_str(state: dict) -> str:
    """组装注入 LLM 的历史上下文: 摘要 + 最近 K 轮原文"""
    active = state.get("_active_conv")
    if not active:
        return ""

    conn = _get_conn(state["db_path"])
    cid = active["conversation_id"]

    turns = conn.execute(
        "SELECT turn_id, query, answer, timestamp FROM turns WHERE conversation_id = ? ORDER BY turn_id",
        (cid,)
    ).fetchall()

    if not turns:
        return ""

    summaries = conn.execute(
        "SELECT turn_range_start, turn_range_end, summary, key_topics, key_decisions FROM summaries WHERE conversation_id = ? ORDER BY turn_range_start",
        (cid,)
    ).fetchall()

    k = config.SUMMARY_WINDOW_K
    parts = []

    # 1. 摘要区
    if summaries:
        parts.append("【对话摘要 - 早期轮次】")
        for s in summaries:
            topics = "、".join(json.loads(s["key_topics"])) if s["key_topics"] else ""
            decisions = "、".join(json.loads(s["key_decisions"])) if s["key_decisions"] else ""
            parts.append(
                f"第{s['turn_range_start']}-{s['turn_range_end']}轮摘要: {s['summary']}"
            )
            if topics:
                parts.append(f"  关键主题: {topics}")
            if decisions:
                parts.append(f"  重要结论: {decisions}")
            parts.append("")
        parts.append("如需查阅以上轮次的完整对话内容，请使用 [TOOL:recall_turn:<轮次号>] 或 [TOOL:recall_range:<起始>-<结束>]")
        parts.append("")

    # 2. 原文区: 最近 K 轮
    recent = list(turns)[-k:] if len(turns) > k else list(turns)
    parts.append("【最近对话】")
    for t in recent:
        ts = ""
        try:
            dt = datetime.fromisoformat(t["timestamp"])
            ts = dt.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
        parts.append(f"用户[{ts}] [轮次{t['turn_id']}]: {t['query']}")
        parts.append(f"助手[{ts}]: {t['answer'][:500]}")
        parts.append("")

    return "\n".join(parts)


# ============================================================
# 工具: 历史查阅
# ============================================================

def recall_turn(state: dict, turn_id: int) -> Optional[str]:
    """查阅指定轮次的完整原文"""
    active = state.get("_active_conv")
    if not active:
        return None

    conn = _get_conn(state["db_path"])
    row = conn.execute(
        "SELECT turn_id, query, answer, timestamp FROM turns WHERE conversation_id = ? AND turn_id = ?",
        (active["conversation_id"], turn_id)
    ).fetchone()

    if not row:
        return None

    ts = ""
    try:
        dt = datetime.fromisoformat(row["timestamp"])
        ts = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        pass

    return (
        f"【历史查阅 - 第{turn_id}轮 ({ts})】\n"
        f"用户: {row['query']}\n\n"
        f"助手: {row['answer']}"
    )


def recall_range(state: dict, start: int, end: int) -> Optional[str]:
    """查阅指定区间的完整原文"""
    active = state.get("_active_conv")
    if not active:
        return None

    conn = _get_conn(state["db_path"])
    rows = conn.execute(
        "SELECT turn_id, query, answer, timestamp FROM turns WHERE conversation_id = ? AND turn_id BETWEEN ? AND ? ORDER BY turn_id",
        (active["conversation_id"], start, end)
    ).fetchall()

    if not rows:
        return None

    parts = [f"【历史查阅 - 第{start}-{end}轮】"]
    for r in rows:
        ts = ""
        try:
            dt = datetime.fromisoformat(r["timestamp"])
            ts = dt.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
        parts.append(f"--- 轮次{r['turn_id']} ({ts}) ---")
        parts.append(f"用户: {r['query']}")
        parts.append(f"助手: {r['answer'][:800]}")
        parts.append("")
    return "\n".join(parts)


# ============================================================
# 任务计划缓冲区
# ============================================================

def get_plan(state: dict) -> Optional[dict]:
    """读取当前任务计划"""
    active = state.get("_active_conv")
    if not active:
        return None

    conn = _get_conn(state["db_path"])
    row = conn.execute(
        "SELECT goal, steps, created_at, updated_at FROM plans WHERE conversation_id = ?",
        (active["conversation_id"],)
    ).fetchone()

    if not row:
        return None

    return {
        "conversation_id": active["conversation_id"],
        "goal": row["goal"],
        "steps": json.loads(row["steps"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_plan(state: dict, action: dict) -> dict:
    """更新任务计划，返回当前计划状态"""
    active = state.get("_active_conv")
    if not active:
        return {"ok": False, "error": "no active conversation"}

    conn = _get_conn(state["db_path"])
    cid = active["conversation_id"]
    now = datetime.now().isoformat()

    row = conn.execute("SELECT goal, steps FROM plans WHERE conversation_id = ?", (cid,)).fetchone()

    if row is None:
        plan = {
            "goal": "",
            "steps": [],
        }
    else:
        plan = {
            "goal": row["goal"],
            "steps": json.loads(row["steps"]),
        }

    # 更新 goal
    if "goal" in action and action["goal"]:
        plan["goal"] = action["goal"]

    # 更新 steps
    if "steps" in action:
        plan["steps"] = action["steps"]
    elif "step_update" in action:
        upd = action["step_update"]
        for s in plan["steps"]:
            if s.get("step_id") == upd.get("step_id"):
                if "status" in upd:
                    s["status"] = upd["status"]
                    if upd["status"] == "completed":
                        s["completed_at"] = now
                break

    plan["updated_at"] = now

    # 检查全部完成
    all_done = all(s.get("status") == "completed" for s in plan["steps"] if s.get("status"))
    if all_done or action.get("complete"):
        conn.execute("DELETE FROM plans WHERE conversation_id = ?", (cid,))
        conn.commit()
        return {"ok": True, "completed": True, "plan": None}

    # upsert
    conn.execute(
        "INSERT INTO plans (conversation_id, goal, steps, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(conversation_id) DO UPDATE SET goal=excluded.goal, steps=excluded.steps, updated_at=excluded.updated_at",
        (cid, plan["goal"], json.dumps(plan["steps"], ensure_ascii=False),
         row["created_at"] if row else now, now)
    )
    conn.commit()

    return {"ok": True, "completed": False, "plan": plan}


def _plan_context_str(plan: Optional[dict]) -> str:
    """将 plan 格式化为 LLM 可读上下文"""
    if not plan or not plan.get("goal"):
        return ""

    lines = ["【当前任务计划】"]
    lines.append(f"目标: {plan['goal']}")
    if plan.get("steps"):
        status_icons = {"completed": "[已完成]", "in_progress": "[进行中]", "pending": "[待执行]"}
        lines.append("步骤:")
        for s in plan["steps"]:
            icon = status_icons.get(s.get("status", "pending"), "")
            lines.append(f"  {icon} 步骤{s.get('step_id', '?')}: {s.get('measure', '')}")
            lines.append(f"         预期结果: {s.get('expected_result', '')}")
    return "\n".join(lines)


# ============================================================
# 会话管理 - 列表 / 详情 / 删除
# ============================================================

def list_user_conversations(state: dict, user_id: str) -> List[dict]:
    """列出某个用户的所有会话摘要"""
    conn = _get_conn(state["db_path"])
    rows = conn.execute(
        "SELECT conversation_id, user_id, turn_counter, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()

    results = []
    for row in rows:
        # 取首条 query 作为标题
        first = conn.execute(
            "SELECT query FROM turns WHERE conversation_id = ? ORDER BY turn_id LIMIT 1",
            (row["conversation_id"],)
        ).fetchone()
        title = first["query"][:40] if first else ""

        results.append({
            "conversation_id": row["conversation_id"],
            "user_id": row["user_id"],
            "title": title,
            "turn_count": row["turn_counter"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return results


def get_conversation_data(state: dict, user_id: str, conversation_id: str) -> Optional[dict]:
    """获取指定会话的完整数据"""
    conn = _get_conn(state["db_path"])
    conv = conn.execute(
        "SELECT conversation_id, user_id, turn_counter, created_at, updated_at FROM conversations WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id)
    ).fetchone()

    if not conv:
        return None

    turns = conn.execute(
        "SELECT turn_id, timestamp, query, answer, meta FROM turns WHERE conversation_id = ? ORDER BY turn_id",
        (conversation_id,)
    ).fetchall()

    return {
        "conversation_id": conv["conversation_id"],
        "user_id": conv["user_id"],
        "turn_counter": conv["turn_counter"],
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
        "turns": [
            {
                "turn_id": t["turn_id"],
                "timestamp": t["timestamp"],
                "query": t["query"],
                "answer": t["answer"],
            }
            for t in turns
        ],
    }


def delete_conversation(state: dict, user_id: str, conversation_id: str) -> bool:
    """删除一个会话及其关联数据"""
    conn = _get_conn(state["db_path"])
    affected = conn.execute(
        "SELECT conversation_id FROM conversations WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id)
    ).fetchone()

    if not affected:
        return False

    conn.execute("DELETE FROM summaries WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM plans WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
    conn.commit()

    active = state.get("_active_conv")
    if active and active.get("conversation_id") == conversation_id:
        state["_active_conv"] = None

    return True


# ============================================================
# 工厂
# ============================================================

def create_session_manager(db_path: str, *,
                           llm_client=None,
                           llm_model: str = "",
                           on_debug=None,
                           log=None) -> SimpleNamespace:
    """创建会话管理模块 (SQLite)

    Args:
        db_path: SQLite 数据库文件路径
        llm_client: LLM 客户端 (用于摘要生成)
        llm_model: LLM 模型名
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - start(user_id, conversation_id, force_new) -> dict
          - add_turn(query, answer, meta) -> int
          - get_context() -> str
          - recall_turn(turn_id) -> str
          - recall_range(start, end) -> str
          - get_plan() -> dict
          - update_plan(action) -> dict
          - plan_context_str() -> str
          - list_conversations(user_id) -> list
          - get_conversation(user_id, cid) -> dict
          - delete_conversation(user_id, cid) -> bool
          - _state: 内部状态
    """
    state = {
        "db_path": str(db_path),
        "llm_client": llm_client,
        "llm_model": llm_model,
        "_active_conv": None,
        "_on_debug": on_debug,
        "_log": log,
    }

    _init_db(state["db_path"])

    return SimpleNamespace(
        start=lambda user_id="default", conversation_id=None, force_new=False: start_conversation(state, user_id, conversation_id, force_new),
        add_turn=lambda q, a, m=None: add_turn_op(state, q, a, m),
        get_context=lambda: get_context_str(state),
        recall_turn=lambda tid: recall_turn(state, tid),
        recall_range=lambda s, e: recall_range(state, s, e),
        get_plan=lambda: get_plan(state),
        update_plan=lambda action: update_plan(state, action),
        plan_context_str=lambda: _plan_context_str(get_plan(state)),
        # 会话管理
        list_conversations=lambda uid: list_user_conversations(state, uid),
        get_conversation=lambda uid, cid: get_conversation_data(state, uid, cid),
        delete_conversation=lambda uid, cid: delete_conversation(state, uid, cid),
        _state=state,
    )
