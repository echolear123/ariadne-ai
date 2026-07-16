"""Markdown 画布插件 - 思维导图 + 卡片笔记布

画布存储: canvases/{canvas_id}.json → {nodes, edges}
每个节点的 data.content 是标准 Markdown 文本
支持: CRUD / 导出 / AI 扩展 / 全局上下文
"""

import json
import uuid
import re
from pathlib import Path
from datetime import datetime

CANVASES_DIR = Path(__file__).parent.parent.parent / "canvases"
CANVASES_DIR.mkdir(parents=True, exist_ok=True)


def tool_call(tool_name: str, arguments: dict) -> dict:
    """插件入口"""
    if tool_name == "get_canvas":
        return _get_canvas(arguments["canvas_id"])
    elif tool_name == "add_node":
        return _add_node(arguments)
    elif tool_name == "add_edge":
        return _add_edge(arguments)
    elif tool_name == "export_markdown":
        return _export_markdown(arguments["canvas_id"])
    elif tool_name == "ai_expand_node":
        return _ai_expand_node(arguments["canvas_id"], arguments["node_id"])
    elif tool_name == "get_canvas_context":
        return _get_canvas_context(arguments["canvas_id"])
    elif tool_name == "summarize_cards":
        return _summarize_cards(arguments["canvas_id"])
    return {"error": f"未知工具: {tool_name}"}


# ============================================================
# 文件读写
# ============================================================

def _load_canvas(canvas_id: str) -> dict:
    path = CANVASES_DIR / f"{canvas_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"id": canvas_id, "title": canvas_id, "nodes": [], "edges": [], "created_at": datetime.now().isoformat()}


def _save_canvas(data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat()
    path = CANVASES_DIR / f"{data['id']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 画布操作
# ============================================================

def _get_canvas(canvas_id: str) -> dict:
    data = _load_canvas(canvas_id)
    # 摘要: 每个节点只返回前 200 字符
    summary = {
        "id": data["id"],
        "title": data.get("title", canvas_id),
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
        "nodes": [
            {
                "id": n["id"], "title": n.get("data", {}).get("title", ""),
                "x": n.get("x", 0), "y": n.get("y", 0),
                "content_preview": n.get("data", {}).get("content", "")[:80]
            }
            for n in data["nodes"]
        ],
        "edges": [
            {"id": e.get("id", ""), "source": e["source"], "target": e["target"], "label": e.get("label", "")}
            for e in data.get("edges", [])
        ],
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }
    return {"canvas": summary}


def _add_node(args: dict) -> dict:
    canvas_id = args["canvas_id"]
    title = args.get("title", "新卡片")
    content = args.get("content", "")
    x = args.get("x", 200)
    y = args.get("y", 200)
    width = args.get("width", 350)
    height = args.get("height", 250)

    data = _load_canvas(canvas_id)
    node_id = f"node_{uuid.uuid4().hex[:8]}"
    node = {
        "id": node_id, "type": "markdown",
        "x": x, "y": y, "width": width, "height": height,
        "data": {"title": title, "content": content},
    }
    data["nodes"].append(node)
    _save_canvas(data)
    return {"status": "ok", "node_id": node_id, "canvas_id": canvas_id}


def _add_edge(args: dict) -> dict:
    canvas_id = args["canvas_id"]
    source_id = args["source_id"]
    target_id = args["target_id"]
    label = args.get("label", "")

    data = _load_canvas(canvas_id)
    # 验证节点存在
    node_ids = {n["id"] for n in data["nodes"]}
    if source_id not in node_ids:
        return {"error": f"源节点不存在: {source_id}"}
    if target_id not in node_ids:
        return {"error": f"目标节点不存在: {target_id}"}

    edge_id = f"edge_{uuid.uuid4().hex[:6]}"
    data.setdefault("edges", []).append({
        "id": edge_id, "source": source_id, "target": target_id, "label": label
    })
    _save_canvas(data)
    return {"status": "ok", "edge_id": edge_id, "canvas_id": canvas_id}


def _export_markdown(canvas_id: str) -> dict:
    """路径二: 画布 → 层级 Markdown"""
    data = _load_canvas(canvas_id)
    edges = data.get("edges", [])
    # 构建邻接关系 (source → targets)
    children = {}
    for e in edges:
        children.setdefault(e["source"], []).append(e["target"])

    # BFS 生成 Markdown
    md_lines = [f"# {data.get('title', canvas_id)}\n"]
    node_map = {n["id"]: n for n in data["nodes"]}

    visited = set()
    roots = [n["id"] for n in data["nodes"] if not any(e["target"] == n["id"] for e in edges)]
    if not roots and data["nodes"]:
        roots = [data["nodes"][0]["id"]]

    def _write_node(node_id: str, depth: int):
        if node_id in visited:
            return
        visited.add(node_id)
        n = node_map.get(node_id)
        if not n:
            return
        prefix = "#" * min(depth + 1, 6)
        title = n.get("data", {}).get("title", node_id)
        content = n.get("data", {}).get("content", "")
        md_lines.append(f"{prefix} {title}")
        if content.strip():
            md_lines.append(content.strip())
        md_lines.append("")
        for child_id in children.get(node_id, []):
            _write_node(child_id, depth + 1)

    for root_id in roots:
        _write_node(root_id, 1)

    return {"markdown": "\n".join(md_lines), "canvas_id": canvas_id}


def _ai_expand_node(canvas_id: str, node_id: str) -> dict:
    """节点单推: 返回节点内容的包装，标记为待 LLM 扩展"""
    data = _load_canvas(canvas_id)
    for n in data["nodes"]:
        if n["id"] == node_id:
            title = n.get("data", {}).get("title", "")
            content = n.get("data", {}).get("content", "")
            # 返回上下文让 LLM 扩展
            prompt_context = (
                f"【待扩展卡片】\n"
                f"标题: {title}\n"
                f"当前内容:\n{content}\n\n"
                f"请围绕这个主题生成扩展内容 (Markdown 格式), "
                f"包含相关概念、要点、示例。输出纯 Markdown，不要额外解释。"
            )
            return {
                "node_id": node_id, "title": title,
                "content": content,
                "ai_prompt": prompt_context,
                "hint": "使用 add_node 工具在画布上创建新卡片，或使用普通对话回复扩展内容"
            }
    return {"error": f"节点不存在: {node_id}"}


def _get_canvas_context(canvas_id: str) -> dict:
    """全局上下文集: 用于 RAG 或 AI 对话"""
    data = _load_canvas(canvas_id)
    edges = data.get("edges", [])
    node_map = {n["id"]: n for n in data["nodes"]}

    # 构建边索引
    adjacency = {}
    for e in edges:
        adjacency.setdefault(e["source"], []).append({
            "target": e["target"],
            "target_title": node_map.get(e["target"], {}).get("data", {}).get("title", e["target"]),
            "label": e.get("label", "→")
        })

    nodes_text = []
    for n in data["nodes"]:
        nd = n.get("data", {})
        connected = adjacency.get(n["id"], [])
        nodes_text.append({
            "id": n["id"],
            "title": nd.get("title", ""),
            "content": nd.get("content", "")[:300],
            "out_edges": connected,
        })

    context = {
        "canvas_id": canvas_id,
        "title": data.get("title", ""),
        "total_nodes": len(data["nodes"]),
        "total_edges": len(edges),
        "nodes": nodes_text,
        "graph_description": _describe_graph(data["nodes"], edges),
    }
    return {"context": context}


def _describe_graph(nodes, edges) -> str:
    """将画布拓扑转为自然语言描述"""
    node_map = {n["id"]: n for n in nodes}
    lines = []
    for e in edges:
        src = node_map.get(e["source"], {})
        tgt = node_map.get(e["target"], {})
        src_title = src.get("data", {}).get("title", e["source"])
        tgt_title = tgt.get("data", {}).get("title", e["target"])
        label = e.get("label", "指向")
        lines.append(f"「{src_title}」{label} 「{tgt_title}」")
    return "；".join(lines) if lines else "无连线关系"


def _summarize_cards(canvas_id: str) -> dict:
    """总结画布上所有卡片内容"""
    data = _load_canvas(canvas_id)
    
    if not data["nodes"]:
        return {"summary": "画布上暂无卡片内容。"}
    
    summaries = []
    for i, n in enumerate(data["nodes"], 1):
        nd = n.get("data", {})
        title = nd.get("title", "未命名卡片")
        content = nd.get("content", "").strip()
        
        if content:
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
            summaries.append(f"{i}. **{title}**\n\n{content_preview}\n")
        else:
            summaries.append(f"{i}. **{title}**\n\n(暂无内容)\n")
    
    edges = data.get("edges", [])
    relations = ""
    if edges:
        relations = "\n---\n\n**卡片关系：**\n" + _describe_graph(data["nodes"], edges)
    
    summary_text = (
        f"## 画布卡片内容总结\n\n"
        f"**画布名称：** {data.get('title', canvas_id)}\n"
        f"**卡片总数：** {len(data['nodes'])}\n"
        f"**连线数量：** {len(edges)}\n\n"
        f"---\n\n"
        f"**卡片详情：**\n\n"
        + "\n".join(summaries)
        + relations
    )
    
    return {"summary": summary_text, "canvas_id": canvas_id, "card_count": len(data["nodes"])}
