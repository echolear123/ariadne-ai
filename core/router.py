"""前台路由 - 函数式架构

检索 → 组装 → 回答 + 工具调用 (PDF提取 / 历史查阅 / 计划更新)。
依赖注入所有子模块。

工厂: create_router(llm_client, auditor, skill_provider, memory_providers, pdf_reader, session, schema, *, on_debug, log)
返回 SimpleNamespace 含: route, _state
"""

import re
import json as _json
import time
from types import SimpleNamespace
from typing import List, Optional, Tuple, Dict

from openai import OpenAI

from interfaces.types import Skill, MemoryEntry, RouteMeta, DebugCallback, LogCallback
from core.context_builder import build_context, build_manifest_context
import config


# ============================================================
# 常量 - 工具指令模式
# ============================================================

TOOL_PDF          = re.compile(r'\[TOOL:read_pdf:([^:]+):(\d+)-(\d+)\]')
TOOL_RECALL_TURN  = re.compile(r'\[TOOL:recall_turn:(\d+)\]')
TOOL_RECALL_RANGE = re.compile(r'\[TOOL:recall_range:(\d+)-(\d+)\]')
TOOL_UPDATE_PLAN  = re.compile(r'\[TOOL:update_plan:(.+)\]')
TOOL_PLUGIN       = re.compile(r'\[PLUGIN:([^:]+):([^\]]+)\]')
TOOL_ANY          = re.compile(r'\[(TOOL|PLUGIN):(\w+):')

QUERY_REWRITE_PROMPT = """你的任务是将用户的追问改写成一个自包含的完整问题。

你有对话历史（最近几轮对话内容）和用户的当前提问。

规则:
1. 如果当前提问包含指代词（"这个"、"那个"、"上述"、"它"、"该文件"等）或是对上一轮的自然延续（"解读正文"、"继续"、"详细说说"等），请将指代消解，改写为不依赖历史也能理解的问题。
2. 如果当前提问完全不依赖对话历史（如"知识库中有什么内容"），原样返回。
3. 只返回改写后的问题文本，不要加任何解释或前缀。

对话历史:
{history}

当前提问: {query}

改写后的问题:"""


def _rewrite_query(llm_client, llm_model: str, query: str, history: str) -> str:
    """用 LLM 将指代追问改写为自包含问题"""
    if not history or not llm_client:
        return query

    # 快判: 不含任何指代词 → 直接返回，不调 LLM
    if not re.search(r'(这个|那个|上述|它|该[文政通办方]|上文|前面|继续|接着|解读.*具体|介绍.*这个|分析.*这个)', query):
        return query

    prompt = QUERY_REWRITE_PROMPT.format(history=history[-1500:], query=query)
    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=200
        )
        rewritten = resp.choices[0].message.content.strip()
        if rewritten and len(rewritten) < 500:
            return rewritten
    except Exception:
        pass
    return query


# ============================================================
# 纯函数 - 检索
# ============================================================

def _retrieve_memory(memory_providers: List, query: str,
                     skill: Optional[Skill] = None,
                     _log_fn=None) -> List[MemoryEntry]:
    """从所有记忆源检索，合并去重"""
    all_entries: List[MemoryEntry] = []
    seen_content: set = set()
    for provider in memory_providers:
        t0 = time.time()
        name = getattr(provider, 'name', provider.__class__.__name__)
        entries = provider.query(query)
        ms = round((time.time() - t0) * 1000)
        if _log_fn:
            _log_fn(f"  [{name}] query → {len(entries)} hits in {ms}ms")
        for entry in entries:
            key = (entry.source, entry.content[:100])
            if key not in seen_content:
                seen_content.add(key)
                all_entries.append(entry)
    return all_entries


def _load_entities(memory_providers: List, entity_refs: List[str]) -> str:
    """加载实体字典"""
    parts = []
    for provider in memory_providers:
        if hasattr(provider, 'read_entity_file'):
            for ref in entity_refs:
                content = provider.read_entity_file(ref)
                if content:
                    parts.append(content)
    return "\n".join(parts)


# ============================================================
# 状态操作
# ============================================================

def _run_tool_loop(state: dict, query: str, skill, memory_entries,
                   entity_context, manifest_context, plan_ctx, on_token,
                   max_loops: int = 3) -> Tuple[str, dict]:
    """工具循环: 检测 [TOOL:...] 指令，执行后重新生成，最多 max_loops 次"""
    llm_client = state["llm_client"]
    llm_model = state["llm_model"]
    schema = state["schema"]
    pdf_reader = state["pdf_reader"]
    session = state.get("session")
    auditor = state["auditor"]

    base_kwargs = dict(
        schema=schema, query=query, skill=skill,
        memory_entries=memory_entries, entity_context=entity_context,
        manifest_context=manifest_context,
    )

    def _build_ctx(extra: dict = None) -> str:
        kw = dict(base_kwargs)
        kw["plan_context"] = session.plan_context_str() if session else ""
        if session:
            kw["history_context"] = session.get_context()
            if kw["history_context"]:
                print(f"  [Session] 历史上下文: {len(kw['history_context'])} 字符")
            else:
                print(f"  [Session] 无历史上下文 (新会话或上下文为空)")
        if extra:
            kw.update(extra)
        return build_context(**kw)

    context = _build_ctx()
    answer = _generate(llm_client, llm_model, schema, context, state, on_token=on_token)

    for loop in range(max_loops):
        if not TOOL_ANY.search(answer):
            break

        tool_result = _execute_tools(state, answer, auditor)
        if not tool_result:
            break

        extra = {}
        if tool_result["type"] == "pdf":
            extra["pdf_page_context"] = tool_result["text"]
            hint = tool_result["hint"]
        elif tool_result["type"] in ("recall_turn", "recall_range"):
            extra["history_context"] = tool_result["text"]
            hint = tool_result["hint"]
        elif tool_result["type"] == "plan_update":
            # 计划更新不需二次生成，但继续检查是否还有其他工具
            continue
        else:
            break

        context2 = _build_ctx(extra)
        answer = _generate(llm_client, llm_model, schema,
                           hint + "\n\n" + context2, state, on_token=on_token)

    return answer, {}


def _execute_tools(state: dict, answer: str, auditor) -> Optional[dict]:
    """检测并执行工具指令，返回工具执行结果"""
    pdf_reader = state["pdf_reader"]
    session = state.get("session")

    # PDF 提取
    m = TOOL_PDF.search(answer)
    if m and pdf_reader:
        filename, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        auditor.log_action("tool_call", {"tool": "read_pdf", "pdf": filename, "pages": f"{start}-{end}"})
        pdf_text = pdf_reader.extract_formatted(filename, start, end, max_chars=4000)
        return {"type": "pdf", "text": pdf_text,
                "hint": f"[系统已提取 {filename} 第 {start}-{end} 页]",
                "detail": {"pdf": filename, "pages": f"{start}-{end}"}}

    # 查阅单轮历史
    m = TOOL_RECALL_TURN.search(answer)
    if m and session:
        turn_id = int(m.group(1))
        text = session.recall_turn(turn_id)
        if text:
            auditor.log_action("tool_call", {"tool": "recall_turn", "turn_id": turn_id})
            return {"type": "recall_turn", "text": text,
                    "hint": f"[系统已查阅第{turn_id}轮对话原文]",
                    "detail": {"turn_id": turn_id}}
        return None

    # 查阅区间历史
    m = TOOL_RECALL_RANGE.search(answer)
    if m and session:
        start, end = int(m.group(1)), int(m.group(2))
        text = session.recall_range(start, end)
        if text:
            auditor.log_action("tool_call", {"tool": "recall_range", "range": f"{start}-{end}"})
            return {"type": "recall_range", "text": text,
                    "hint": f"[系统已查阅第{start}-{end}轮对话原文]",
                    "detail": {"start": start, "end": end}}
        return None

    # 更新计划
    m = TOOL_UPDATE_PLAN.search(answer)
    if m and session:
        payload_str = m.group(1).strip()
        try:
            action = _json.loads(payload_str)
        except _json.JSONDecodeError:
            return None
        result = session.update_plan(action)
        auditor.log_action("tool_call", {"tool": "update_plan", "result": result.get("ok")})
        if result.get("ok"):
            return {"type": "plan_update"}

    # 插件调用: [PLUGIN:插件名.工具名:{"arg":"val"}]
    m = TOOL_PLUGIN.search(answer)
    if m:
        full_name = m.group(1).strip()
        args_str = m.group(2).strip()
        try:
            args = _json.loads(args_str)
        except _json.JSONDecodeError:
            args = {"value": args_str}
        plugin_loader = state.get("plugin_loader")
        if plugin_loader:
            result = plugin_loader.mcp_call_tool(full_name, args)
            auditor.log_action("tool_call", {"tool": "plugin", "plugin_tool": full_name, "args": str(args)[:100]})
            result_text = _json.dumps(result, ensure_ascii=False)
            return {"type": "plugin", "text": result_text,
                    "hint": f"[插件: {full_name} 执行结果]",
                    "detail": {"plugin_tool": full_name, "result": result_text[:1000]}}
        return None

    return None


def route_query(state: dict, query: str, on_token=None) -> Tuple[str, dict]:
    """主路由: 检索 → 组装 → 回答 (含工具循环)"""
    auditor = state["auditor"]
    skill_provider = state["skill_provider"]
    memory_providers = state["memory_providers"]
    session = state.get("session")
    llm_client = state["llm_client"]
    llm_model = state["llm_model"]
    schema = state["schema"]
    metadata = state["metadata"]
    _log = state.get("_log")

    def _console(step, ms, extra=""):
        line = f"  [计时] {step}: {ms}ms {extra}"
        print(line)
        if _log:
            _log("timing", "INFO", step + f" {ms}ms")

    meta_dict = {"query": query, "debug": []}
    auditor.log_action("query", {"query": query})

    t0 = time.time()

    # 1. 技能匹配
    t = time.time()
    skill = skill_provider.match(query)
    meta_dict["skill"] = skill.name if skill else None
    _console("技能匹配", round((time.time() - t) * 1000),
             f"→ {skill.name}" if skill else "→ (无)")

    # 2. 实体上下文
    t = time.time()
    entity_context = ""
    if skill and skill.entity_refs:
        entity_context = _load_entities(memory_providers, skill.entity_refs)
    if entity_context:
        _console("实体加载", round((time.time() - t) * 1000), f"({len(entity_context)} chars)")

    # 3. 记忆检索 — LLM 查询重写（所有问题都走完整检索+生成流程）
    history_str = session.get_context() if session else ""
    t1 = time.time()

    # 用 LLM 改写指代追问为自包含问题（无历史则跳过）
    rewritten_query = _rewrite_query(llm_client, llm_model, query, history_str)
    if rewritten_query != query:
        _console("查询改写", 0, f"\"{query[:30]}...\" → \"{rewritten_query[:60]}...\"")

    memory_entries = _retrieve_memory(memory_providers, rewritten_query, skill, _log_fn=print)
    _console("检索记忆 (总)", round((time.time() - t1) * 1000),
             f"→ {len(memory_entries)} entries")

    meta_dict["debug"].append({
        "step": "检索记忆",
        "count": len(memory_entries),
        "sources": list(set(e.source for e in memory_entries)),
        "ms": round((time.time() - t1) * 1000)
    })
    meta_dict["memory_sources"] = list(set(e.source for e in memory_entries))
    meta_dict["memory_count"] = len(memory_entries)
    if rewritten_query != query:
        meta_dict["rewritten_query"] = rewritten_query

    # 5. 上下文
    t = time.time()
    manifest_context = build_manifest_context(metadata["fast_memory_dir"])
    plan_ctx = session.plan_context_str() if session else ""
    _console("manifest+plan", round((time.time() - t) * 1000))

    # 6. LLM 生成 (含工具循环)
    t_gen = time.time()
    answer, _ = _run_tool_loop(
        state, query, skill, memory_entries,
        entity_context, manifest_context, plan_ctx, on_token
    )
    gen_ms = round((time.time() - t_gen) * 1000)
    _console("LLM 生成 (含工具)", gen_ms, f"→ {len(answer)} chars")
    meta_dict["debug"].append({
        "step": "LLM 生成",
        "answer_len": len(answer),
        "ms": gen_ms
    })

    total_ms = round((time.time() - t0) * 1000)
    meta_dict["debug"].append({"step": "总耗时", "ms": total_ms})
    _console("总计", total_ms, "")
    print("-" * 40)

    # 7. 记录历史 (session 替代旧 history)
    if session:
        session.add_turn(query, answer, meta_dict)

    auditor.log_action("response", {
        "query": query,
        "answer_preview": answer[:200],
        "meta": meta_dict
    })

    return answer, meta_dict


def _generate(llm_client, llm_model: str, schema: str, context: str,
              state: dict = None, on_token=None) -> str:
    """调用 LLM 生成回答 (支持流式回调)"""
    try:
        if on_token:
            # 流式模式: 逐 chunk 回调, 同时累积完整文本
            stream = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": schema},
                    {"role": "user", "content": context}
                ],
                temperature=0.3,
                max_tokens=2048,
                stream=True
            )
            full = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full.append(token)
                    on_token(token)
            return "".join(full)
        else:
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": schema},
                    {"role": "user", "content": context}
                ],
                temperature=0.3,
                max_tokens=2048
            )
            return response.choices[0].message.content
    except Exception as e:
        err = f"[LLM 调用失败: {e}]\n\n以下是检索到的上下文供参考:\n{context[:1000]}"
        if state and state.get("_on_debug"):
            state["_on_debug"]("router", "llm_error", {"error": str(e)})
        return err


# ============================================================
# 工厂
# ============================================================

def create_router(llm_client,
                  auditor,
                  skill_provider,
                  memory_providers: List,
                  pdf_reader=None,
                  session=None,
                  schema: str = "",
                  plugin_loader=None,
                  metadata: dict = None,
                  *,
                  on_debug: DebugCallback = None,
                  log: LogCallback = None) -> SimpleNamespace:
    """创建查询路由模块

    Args:
        llm_client: OpenAI 客户端实例
        auditor: create_audit_logger 返回的审计模块
        skill_provider: create_skill_loader 返回的技能模块
        memory_providers: [fast_memory, long_memory] 列表
        pdf_reader: create_pdf_reader 返回的 PDF 工具 (可选)
        session: create_session_manager 返回的会话管理模块
        schema: 系统指令文本
        metadata: 额外元数据字典 {fast_memory_dir, ...}
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - route(query, on_token) -> (answer, meta): 执行查询路由
          - llm_client: 底层 LLM 客户端 (可复用)
          - _state: 内部状态 (调试用)
    """
    state = {
        "llm_client": llm_client,
        "llm_model": config.LLM_MODEL,
        "auditor": auditor,
        "skill_provider": skill_provider,
        "memory_providers": sorted(memory_providers,
                                   key=lambda p: getattr(p, 'priority', lambda: 99)() if callable(getattr(p, 'priority', None)) else getattr(p, 'priority', 99)),
        "pdf_reader": pdf_reader,
        "session": session,
        "schema": schema,
        "plugin_loader": plugin_loader,
        "metadata": metadata or {},
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        route=lambda query, on_token=None: route_query(state, query, on_token=on_token),
        llm_client=llm_client,
        # 扩展/调试接口
        _state=state,
    )
