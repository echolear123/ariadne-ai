"""Agent Web 服务 - Flask + React 前端

启动: python app.py
前端开发: cd frontend && npm run dev (端口 3000, 代理 API 到 7860)
前端构建: cd frontend && npm run build → 静态文件输出到 ../static
访问: http://localhost:7860
"""

import sys
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from core.agent import create_agent
import config

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# 懒加载 Agent
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        print("[Agent] 正在初始化函数式 Agent (ZVec + Wiki)...")
        _agent = create_agent()
        print("[Agent] 初始化完成")
    return _agent


# ================================================================
# 静态文件服务 (React 构建产物)
# ================================================================

STATIC_DIR = Path(__file__).parent / "static"


@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(str(STATIC_DIR / "assets"), filename)


# ================================================================
# 用户登录 - 用户名+密码验证
# ================================================================

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username:
        return jsonify({"error": "用户名不能为空"}), 400
    if not password:
        return jsonify({"error": "密码不能为空"}), 400

    # 验证用户名密码
    expected_password = config.USERS.get(username)
    if expected_password is None:
        return jsonify({"error": "用户名或密码错误"}), 401
    if password != expected_password:
        return jsonify({"error": "用户名或密码错误"}), 401

    user_id = username
    return jsonify({"user_id": user_id, "username": username, "status": "ok"})


# ================================================================
# 插件 API
# ================================================================

@app.route("/api/plugins", methods=["GET"])
def list_plugins():
    ag = get_agent()
    return jsonify(ag.plugin_loader.list_plugins())


@app.route("/api/plugins/<plugin_name>/<tool_name>", methods=["POST"])
def call_plugin_tool(plugin_name, tool_name):
    ag = get_agent()
    data = request.get_json() or {}
    full_name = f"{plugin_name}.{tool_name}"
    result = ag.plugin_loader.mcp_call_tool(full_name, data)
    return jsonify(result)


# ================================================================
# 画布 API (Markdown Canvas)
# ================================================================

CANVASES_DIR = config.BASE_DIR / "canvases"
CANVASES_DIR.mkdir(parents=True, exist_ok=True)

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/api/canvases", methods=["GET"])
def list_canvases():
    files = sorted(CANVASES_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "id": data["id"],
                "title": data.get("title", ""),
                "node_count": len(data.get("nodes", [])),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            pass
    return jsonify(result)


@app.route("/api/canvas/<canvas_id>", methods=["GET"])
def get_canvas(canvas_id):
    path = CANVASES_DIR / f"{canvas_id}.json"
    if not path.exists():
        return jsonify({"id": canvas_id, "title": canvas_id, "nodes": [], "edges": []})
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@app.route("/api/canvas", methods=["POST"])
def create_canvas():
    import uuid
    data = request.get_json() or {}
    canvas_id = f"canvas_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'timezone') else datetime.now().isoformat()
    canvas_data = {
        "id": canvas_id,
        "title": data.get("title", "新画布"),
        "nodes": [],
        "edges": [],
        "created_at": now,
        "updated_at": now,
    }
    path = CANVASES_DIR / f"{canvas_id}.json"
    path.write_text(json.dumps(canvas_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(canvas_data)


@app.route("/api/canvas/<canvas_id>", methods=["PUT"])
def update_canvas(canvas_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效数据"}), 400
    data["id"] = canvas_id
    now = datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'timezone') else datetime.now().isoformat()
    data["updated_at"] = now
    if "created_at" not in data:
        existing_path = CANVASES_DIR / f"{canvas_id}.json"
        if existing_path.exists():
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            data["created_at"] = existing.get("created_at", now)
        else:
            data["created_at"] = now
    path = CANVASES_DIR / f"{canvas_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "canvas_id": canvas_id})


@app.route("/api/canvas/<canvas_id>", methods=["DELETE"])
def delete_canvas_api(canvas_id):
    path = CANVASES_DIR / f"{canvas_id}.json"
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})


# ================================================================
# 会话管理 API
# ================================================================

@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    user_id = request.headers.get("X-User-Id", "default")
    sessions = get_agent().session.list_conversations(user_id)
    return jsonify(sessions)


@app.route("/api/conversation/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id):
    user_id = request.headers.get("X-User-Id", "default")
    data = get_agent().session.get_conversation(user_id, conversation_id)
    if not data:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify(data)


@app.route("/api/conversation/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id):
    user_id = request.headers.get("X-User-Id", "default")
    ok = get_agent().session.delete_conversation(user_id, conversation_id)
    return jsonify({"ok": ok})


# ================================================================
# 对话核心 API (SSE 流式)
# ================================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    query = data.get("message", "").strip()
    user_id = data.get("user_id") or request.headers.get("X-User-Id", "default")
    conversation_id = data.get("conversation_id", None)
    if not query:
        return jsonify({"error": "消息不能为空"}), 400

    def generate():
        from collections import deque
        import threading, time

        ag = get_agent()
        token_queue = deque()
        result = {"answer": None, "meta": None, "error": None,
                  "conversation_id": conversation_id}

        def on_token(token: str):
            token_queue.append(token)

        def _run():
            try:
                # conversation_id=None 表示前端要新建会话 → force_new
                info = ag.session.start(
                    user_id=user_id, conversation_id=conversation_id,
                    force_new=(conversation_id is None)
                )
                result["conversation_id"] = info["conversation_id"]
                result["answer"], result["meta"] = ag.router.route(
                    query, on_token=on_token
                )
            except Exception as e:
                result["error"] = str(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        thread_alive = True
        while thread_alive:
            thread_alive = thread.is_alive()
            while token_queue:
                tok = token_queue.popleft()
                yield f"event: token\ndata: {json.dumps({'text': tok})}\n\n"
            if thread_alive:
                time.sleep(0.02)

        while token_queue:
            tok = token_queue.popleft()
            yield f"event: token\ndata: {json.dumps({'text': tok})}\n\n"

        if result["error"]:
            yield f"event: error\ndata: {json.dumps({'message': result['error']})}\n\n"
            yield "event: done\ndata: {}\n\n"
        else:
            answer, meta = result["answer"], result["meta"]
            cid = result.get("conversation_id")
            yield f"event: done\ndata: {json.dumps({'debug': meta.get('debug', []), 'conversation_id': cid})}\n\n"

            threading.Thread(
                target=ag.reviewer.review,
                args=(query, answer, meta),
                daemon=True
            ).start()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ================================================================
# 管理 API (保留原有)
# ================================================================

@app.route("/api/correct", methods=["POST"])
def correct():
    data = request.get_json()
    get_agent().correct(data["keyword"], data["content"])
    return jsonify({"status": "ok"})


@app.route("/api/reload", methods=["POST"])
def reload_skills():
    get_agent().reload_skills()
    return jsonify({"status": "ok"})


@app.route("/api/audit", methods=["GET"])
def audit():
    return jsonify({"logs": get_agent().audit_report(limit=50)})


@app.route("/api/index", methods=["POST"])
def index_docs():
    get_agent().index_source_documents()
    return jsonify({"status": "ok"})


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    filepath = UPLOADS_DIR / filename
    print(f"[IMG] serve_upload 请求: filename={filename}, exists={filepath.exists()}, path={filepath}")
    return send_from_directory(str(UPLOADS_DIR), filename)


@app.route("/api/upload-document", methods=["POST"])
def upload_document():
    """上传文档到知识库，自动解析并入库到向量库"""
    if 'file' not in request.files:
        return jsonify({"error": "没有文件"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "没有选择文件"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in {'.pdf', '.docx', '.txt', '.md'}:
        return jsonify({"error": f"不支持的文档格式: {ext}，支持 PDF/DOCX/TXT/MD"}), 400

    # 保存到 source/ 目录
    source_dir = config.SOURCE_DIR
    source_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename
    filepath = source_dir / filename
    # 如果同名文件已存在，加上时间戳后缀
    if filepath.exists():
        stem = Path(filename).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stem}_{timestamp}{ext}"
        filepath = source_dir / filename
    file.save(str(filepath))

    # 自动入库到向量库
    ag = get_agent()
    result = ag.index_single_document(str(filepath))

    if result.get("ok"):
        return jsonify({
            "status": "ok",
            "filename": filename,
            "chunks": result["chunks"],
            "message": f"文档 '{filename}' 已成功入库，共 {result['chunks']} 个文本块"
        })
    else:
        return jsonify({
            "status": "error",
            "filename": filename,
            "error": result.get("error", "入库失败")
        }), 500


# ================================================================
# 文档管理 API
# ================================================================

NOTES_PATH = config.FAST_MEMORY_DIR / "docs_index" / "doc_notes.json"


@app.route("/api/documents", methods=["GET"])
def list_documents():
    """列出所有已入库文档"""
    ag = get_agent()
    source_dir = config.SOURCE_DIR
    docs = []
    notes = {}
    if NOTES_PATH.exists():
        try:
            notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    if source_dir.exists():
        for f in sorted(source_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in {'.pdf', '.docx', '.txt', '.md'}:
                stat = f.stat()
                docs.append({
                    "filename": f.name,
                    "size": stat.st_size,
                    "size_display": _format_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "notes": notes.get(f.name, ""),
                })
    return jsonify(docs)


@app.route("/api/document/<path:filename>/download", methods=["GET"])
def download_document(filename):
    """下载原始文档"""
    filepath = config.SOURCE_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404
    return send_from_directory(str(config.SOURCE_DIR), filename, as_attachment=True)


@app.route("/api/document/<path:filename>", methods=["DELETE"])
def delete_document_api(filename):
    """删除文档及向量条目"""
    ag = get_agent()
    result = ag.delete_document(filename)
    if result.get("ok"):
        return jsonify(result)
    return jsonify(result), 404 if "不存在" in str(result.get("error", "")) else 500


@app.route("/api/document/<path:filename>/notes", methods=["PUT"])
def update_document_notes_api(filename):
    """更新文档备注"""
    data = request.get_json()
    notes_text = (data.get("notes") or "").strip()
    ag = get_agent()
    result = ag.update_document_notes(filename, notes_text)
    return jsonify(result)


def _format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


# ================================================================
# 向量库管理 API
# ================================================================

@app.route("/api/vector-entries", methods=["GET"])
def list_vector_entries():
    """列出向量库中的所有条目"""
    ag = get_agent()
    source = request.args.get("source", "")
    entries = ag.vector_store.list_entries(source_filter=source if source else None)
    return jsonify({
        "total": len(entries),
        "entries": entries,
    })


@app.route("/api/vector-entry/<path:doc_id>", methods=["DELETE"])
def delete_vector_entry(doc_id):
    """删除单条向量条目"""
    ag = get_agent()
    ok = ag.vector_store.delete_entry(doc_id)
    if ok:
        return jsonify({"ok": True, "id": doc_id})
    return jsonify({"ok": False, "error": "条目不存在"}), 404


@app.route("/api/vector-stats", methods=["GET"])
def vector_stats():
    """向量库统计信息"""
    ag = get_agent()
    total = ag.vector_store.count()
    # 按 source 分组统计
    sources = {}
    for doc_id, meta in ag.vector_store._state["_text_store"].items():
        src = meta.get("source", "(unknown)")
        sources[src] = sources.get(src, 0) + 1
    return jsonify({
        "total_entries": total,
        "total_sources": len(sources),
        "sources": sources,
    })


@app.route("/api/vector-optimize", methods=["POST"])
def vector_optimize():
    """重建向量索引（批量删除后调用）"""
    ag = get_agent()
    try:
        ag.vector_store._state["_collection"].optimize()
        return jsonify({"ok": True, "message": "索引已重建"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def upload_file():
    print(f"[IMG] upload_file 请求收到, files={list(request.files.keys())}, content_type={request.content_type}")
    if 'file' not in request.files:
        print(f"[IMG] 错误: 没有 file 字段, keys={list(request.files.keys())}")
        return jsonify({"error": "没有文件"}), 400
    file = request.files['file']
    if file.filename == '':
        print("[IMG] 错误: 文件名为空")
        return jsonify({"error": "没有选择文件"}), 400
    
    ext = Path(file.filename).suffix.lower()
    print(f"[IMG] 文件名={file.filename}, ext={ext}")
    if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}:
        print(f"[IMG] 错误: 不支持的格式 {ext}")
        return jsonify({"error": f"不支持的文件格式: {ext}"}), 400
    
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = UPLOADS_DIR / filename
    print(f"[IMG] 保存到: {filepath}")
    file.save(str(filepath))
    
    # 验证文件是否写入成功
    exists = filepath.exists()
    size = filepath.stat().st_size if exists else 0
    print(f"[IMG] 保存结果: exists={exists}, size={size}")
    
    url = f"/uploads/{filename}"
    print(f"[IMG] ✓ 上传成功: url={url}")
    return jsonify({"url": url, "filename": filename})


# SPA fallback: 所有非 API 路径返回 React index.html (必须放在最后)
@app.route("/<path:path>")
def spa_fallback(path):
    if path.startswith("uploads"):
        print(f"[IMG] SPA fallback 拦截了 uploads 路径! path={path} - 这不应该发生")
    if not path.startswith("api") and not path.startswith("uploads"):
        return send_from_directory(str(STATIC_DIR), "index.html")
    return "Not found", 404


if __name__ == "__main__":
    print("=" * 50)
    print(f"  Agent Web 服务")
    print(f"  模型: {config.LLM_MODEL}  |  ZVec + bge-large-zh-v1.5")
    print(f"  React 前端已构建完毕")
    print(f"  打开浏览器访问: http://localhost:{config.WEB_PORT}")
    print("=" * 50)
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False, use_reloader=False)
