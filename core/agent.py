"""Agent 主编排器 - 函数式架构

负责组装所有模块，提供统一对外接口。
所有子模块通过依赖注入组合，无隐式全局状态。

工厂: create_agent(*, on_debug=None, log=None)
返回 SimpleNamespace 含: ask, clear_history, correct, reload_skills, audit_report, index_source_documents, _state

测试方式:
    agent = create_agent()
    print(agent.ask("你的问题"))
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Optional, List

from openai import OpenAI

# 函数式模块工厂
from audit.logger import create_audit_logger
from memory.fast_memory import create_fast_memory
from memory.long_memory import create_long_memory
from memory.vector_store import create_vector_store
from skills.loader import create_skill_loader
from plugins.loader import create_plugin_loader
from tools.pdf_page_reader import create_pdf_reader
from doc_reader import create_doc_reader
from source.source_manifest import create_source_manifest
from core.session import create_session_manager
from core.router import create_router
from core.reviewer import create_reviewer

from interfaces.types import DebugCallback, LogCallback
import config


def create_agent(*,
                 on_debug: DebugCallback = None,
                 log: LogCallback = None) -> SimpleNamespace:
    """创建完整的文档问答 Agent

    所有的子模块通过工厂创建并注入依赖。每个模块均可独立测试和替换。

    Args:
        on_debug: 全局调试回调 (module, action, detail)
        log: 全局日志回调 (action, level, detail_str)

    Returns:
        SimpleNamespace with:
          - ask(query) -> str: 问答
          - clear_history(): 清空对话
          - correct(keyword, content): 添加纠错
          - reload_skills(): 热重载技能
          - audit_report(limit) -> List[dict]: 审计报告
          - index_source_documents() -> int: 全量索引
          - _state: 内部状态 (调试用，含所有子模块引用)
    """

    # 统一日志回调 (审计 + 控制台打印)
    def _system_log(action: str, level: str, detail: str):
        if log:
            log(action, level, detail)
        # 控制台输出关键操作
        if level in ("INFO",):
            print(f"  [{action}] {detail}")

    # ---- 审计层 ----
    auditor = create_audit_logger(
        config.AUDIT_LOG_PATH,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 快记忆 ----
    fast_memory = create_fast_memory(
        config.FAST_MEMORY_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 向量库 ----
    vector_store = create_vector_store(
        config.ZVEC_DIR,
        emb_api_key=config.LLM_API_KEY,
        emb_base_url=config.LLM_BASE_URL,
        embedding_model=config.EMBEDDING_MODEL,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 长记忆 ----
    long_memory = create_long_memory(
        vector_store,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 记忆提供者列表 ----
    memory_providers = [fast_memory, long_memory]

    # ---- 文档工具 ----
    doc_reader = create_doc_reader(
        config.SOURCE_DIR,
        config.DOCS_INDEX_DIR,
        knowledge_base_dir=config.KNOWLEDGE_BASE_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 源文件清单 ----
    manifest = create_source_manifest(
        config.SOURCE_DIR,
        config.FAST_MEMORY_DIR / "source_manifest.md",
        knowledge_base_dir=config.KNOWLEDGE_BASE_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- PDF 工具 ----
    pdf_reader = create_pdf_reader(
        config.SOURCE_DIR,
        knowledge_base_dir=config.KNOWLEDGE_BASE_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 技能 ----
    skill_provider = create_skill_loader(
        config.SKILLS_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 插件 ----
    plugin_loader = create_plugin_loader(
        config.PLUGINS_DIR,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- LLM 客户端 ----
    import httpx
    llm_client = OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
        timeout=httpx.Timeout(timeout=60.0, connect=10.0, read=30.0, write=10.0),
        max_retries=1
    )

    # ---- 对话历史 (会话管理器 SQLite) ----
    session = create_session_manager(
        config.SESSIONS_DB,
        llm_client=llm_client,
        llm_model=config.LLM_MODEL,
        on_debug=on_debug,
        log=_system_log
    )

    # ---- Schema ----
    schema = fast_memory.read_schema()

    # ---- 路由 ----
    router = create_router(
        llm_client=llm_client,
        auditor=auditor,
        skill_provider=skill_provider,
        memory_providers=memory_providers,
        pdf_reader=pdf_reader,
        session=session,
        schema=schema,
        plugin_loader=plugin_loader,
        metadata={"fast_memory_dir": config.FAST_MEMORY_DIR},
        on_debug=on_debug,
        log=_system_log
    )

    # ---- 审查 ----
    reviewer = create_reviewer(
        llm_client=llm_client,
        auditor=auditor,
        fast_memory=fast_memory,
        long_memory=long_memory,
        schema=schema,
        on_debug=on_debug,
        log=_system_log
    )

    # ================================================================
    # 对外接口
    # ================================================================

    # 使用可变容器在闭包间共享 conversation_id
    _conv = {"user_id": "default", "conversation_id": None}

    def ask(query: str, user_id: str = "default",
            conversation_id: str = None) -> str:
        """问答接口: 检索 + 生成 + 审查 (审查不阻塞返回)

        Args:
            query: 用户问题
            user_id: 用户标识 (默认 "default")
            conversation_id: 指定会话 ID (None 则沿用上一轮的会话)
        """
        if conversation_id is not None:
            _conv["user_id"] = user_id
            _conv["conversation_id"] = conversation_id
        elif _conv["conversation_id"] is None:
            _conv["user_id"] = user_id
        info = session.start(user_id=_conv["user_id"], conversation_id=_conv["conversation_id"])
        _conv["conversation_id"] = info["conversation_id"]  # 首次调用时记录自动生成的 ID
        answer, meta = router.route(query)
        # 后台审查, 不阻塞回答返回
        import threading
        threading.Thread(
            target=reviewer.review,
            args=(query, answer, meta),
            daemon=True
        ).start()
        return answer

    def clear_history():
        """清空当前会话 (创建新会话)"""
        _conv["conversation_id"] = None
        info = session.start(force_new=True)
        _conv["conversation_id"] = info["conversation_id"]

    def correct(keyword: str, corrected_content: str):
        fast_memory.add_correction(keyword, corrected_content)
        auditor.log_action("correction", {"keyword": keyword, "content": corrected_content})

    def reload_skills():
        skill_provider.reload()
        auditor.log_action("reload", {"module": "skills"})

    def audit_report(action: Optional[str] = None, limit: int = 100):
        return auditor.query(action=action, limit=limit)

    def index_source_documents() -> int:
        _system_log("index", "INFO", "正在扫描源文件目录...")
        report = manifest.refresh()
        print(f"  [索引] 源文件清单已更新\n{report}")

        _system_log("index", "INFO", "逐个提取文档文本...")
        all_chunks = doc_reader.scan_to_chunks()

        if not all_chunks:
            _system_log("index", "WARN", "无有效文档文本")
        else:
            print(f"  [索引] 共 {len(all_chunks)} 个文本块，正在写入 ZVec...")
            cards = fast_memory.get_docs_index_cards()
            print(f"  [索引] 共 {len(cards)} 个文档骨架卡片")
            long_memory.rebuild(all_chunks, cards)
            print(f"  [索引] ZVec 中现有 {long_memory.count()} 条记录")

        print(f"  [索引] 完成！共 {len(all_chunks)} 个文档切片")
        return len(all_chunks)

    def index_single_document(filepath: str) -> dict:
        """入库单个文档: 提取文本 → 切片 → 写入向量库 (增量追加)

        Args:
            filepath: 文档文件路径 (PDF/DOCX/MD)

        Returns:
            dict: {"ok": True/False, "chunks": int, "filename": str, "error": str}
        """
        fp = Path(filepath)
        if not fp.exists():
            return {"ok": False, "chunks": 0, "filename": fp.name, "error": "文件不存在"}

        suffix = fp.suffix.lower()
        if suffix not in (".pdf", ".docx", ".txt", ".md"):
            return {"ok": False, "chunks": 0, "filename": fp.name,
                    "error": f"不支持的文件格式: {suffix}"}

        try:
            chunks, card = doc_reader.process_single_file(fp)
            if not chunks:
                return {"ok": False, "chunks": 0, "filename": fp.name,
                        "error": "无法提取文档文本或文本为空"}

            # 增量写入向量库
            vector_store.add_chunks(chunks)
            if card:
                vector_store.index_docs_index([card])

            # 刷新源文件清单
            manifest.refresh()

            _system_log("index", "INFO",
                        f"single doc indexed: {fp.name} → {len(chunks)} chunks")
            return {"ok": True, "chunks": len(chunks), "filename": fp.name}

        except Exception as e:
            _system_log("index", "ERROR", f"failed: {fp.name} - {e}")
            return {"ok": False, "chunks": 0, "filename": fp.name, "error": str(e)}

    # ---- 文档备注存储 ----
    import json as _json
    NOTES_PATH = config.FAST_MEMORY_DIR / "docs_index" / "doc_notes.json"

    def _load_notes() -> dict:
        if NOTES_PATH.exists():
            try:
                return _json.loads(NOTES_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_notes(notes: dict):
        NOTES_PATH.write_text(_json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete_document(filename: str) -> dict:
        """删除文档: 源文件 + 向量条目 + 卡片 + 备注"""
        fp = config.SOURCE_DIR / filename
        if not fp.exists():
            # 也尝试 knowledge_base
            found = None
            for f in config.SOURCE_DIR.rglob(filename):
                found = f
                break
            if not found:
                return {"ok": False, "error": "文件不存在"}
            fp = found

        try:
            # 计算卡片名称
            import hashlib
            card_base = filename.replace("/", "_").replace("\\", "_")
            for ext in (".md", ".pdf", ".docx", ".txt"):
                if card_base.endswith(ext):
                    card_base = card_base.rsplit(".", 1)[0]
            card_name = card_base + ".md"
            card_source = f"docs_index/{card_name}"
            card_id = "card_" + hashlib.md5(card_name.encode()).hexdigest()[:16]

            # 1. 删除文档切片向量条目
            n1 = vector_store.delete_by_source(filename)
            print(f"  [删除] 文档切片: {n1} 条")

            # 2. 删除卡片向量条目（_text_store 中 source 为 docs_index/xxx.md）
            n2 = vector_store.delete_by_source(card_source)
            print(f"  [删除] 文档卡片: {n2} 条")

            # 3. 删除卡片文件
            card_path = config.DOCS_INDEX_DIR / card_name
            if card_path.exists():
                card_path.unlink()
                print(f"  [删除] 卡片文件: {card_name}")

            # 4. 删除备注
            notes = _load_notes()
            notes.pop(filename, None)
            _save_notes(notes)

            # 5. 删除源文件
            fp.unlink()

            # 6. 刷新清单
            manifest.refresh()

            _system_log("index", "INFO", f"deleted document: {filename} ({n1} chunks + {n2} cards)")
            return {"ok": True, "filename": filename, "chunks_deleted": n1, "cards_deleted": n2}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_document_notes(filename: str, notes_text: str) -> dict:
        """更新文档备注"""
        notes = _load_notes()
        notes[filename] = notes_text
        _save_notes(notes)
        return {"ok": True, "filename": filename}

    # ================================================================
    # 组装返回
    # ================================================================

    state = {
        "auditor": auditor,
        "fast_memory": fast_memory,
        "long_memory": long_memory,
        "vector_store": vector_store,
        "memory_providers": memory_providers,
        "doc_reader": doc_reader,
        "manifest": manifest,
        "pdf_reader": pdf_reader,
        "skill_provider": skill_provider,
        "session": session,
        "llm_client": llm_client,
        "router": router,
        "plugin_loader": plugin_loader,
        "reviewer": reviewer,
    }

    return SimpleNamespace(
        ask=ask,
        clear_history=clear_history,
        correct=correct,
        reload_skills=reload_skills,
        audit_report=audit_report,
        index_source_documents=index_source_documents,
        index_single_document=index_single_document,
        delete_document=delete_document,
        update_document_notes=update_document_notes,
        # 直接暴露子模块，方便调试和扩展
        router=router,
        plugin_loader=plugin_loader,
        reviewer=reviewer,
        auditor=auditor,
        fast_memory=fast_memory,
        long_memory=long_memory,
        session=session,
        skill_provider=skill_provider,
        pdf_reader=pdf_reader,
        llm_client=llm_client,
        vector_store=vector_store,
        # 扩展/调试接口
        _state=state,
    )
