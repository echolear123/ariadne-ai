"""ZVec 向量库 - 函数式架构

基于 ZVec 本地向量存储 + 硅基流动 bge-large-zh-v1.5 Embedding

工厂: create_vector_store(persist_dir, *, emb_api_key, emb_base_url, embedding_model, on_debug=None, log=None)
返回 SimpleNamespace 含: search, keyword_search, add_chunks, add_faq, remove_faq, rebuild, count, _state
"""

import os
import re
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict

try:
    import zvec
    HAS_ZVEC = True
except ImportError:
    HAS_ZVEC = False

from openai import OpenAI

from interfaces.types import DebugCallback, LogCallback, ChunkSpec


# ============================================================
# 常量
# ============================================================

DIM = 1024
BATCH_SIZE = 20
WRITE_BATCH = 1000


# ============================================================
# 纯函数 - Embedding
# ============================================================

def _embed(emb_client, embedding_model: str, texts: List[str]) -> List[List[float]]:
    """批量 Embedding (批次间 0.3 秒间隔避免 API 限流)"""
    import time as _t
    all_vecs = []
    for i in range(0, len(texts), BATCH_SIZE):
        resp = emb_client.embeddings.create(
            model=embedding_model,
            input=texts[i:i + BATCH_SIZE]
        )
        all_vecs.extend(d.embedding for d in resp.data)
        if i + BATCH_SIZE < len(texts):
            _t.sleep(0.3)
    return all_vecs


# ============================================================
# 状态操作 - 初始化和打开
# ============================================================

def _open_or_create(state: dict) -> None:
    """打开已有 ZVec 数据库，只在数据损坏或首次使用时创建"""
    if state.get("_collection") is not None or not HAS_ZVEC:
        return

    persist_dir = state["persist_dir"]
    manifest = os.path.join(persist_dir, "manifest.0")

    if os.path.exists(manifest):
        try:
            state["_collection"] = zvec.open(path=persist_dir)
            _load_text_store(state)
            return
        except Exception:
            if state.get("_on_debug"):
                state["_on_debug"]("vector_store", "open_failed", {"retry": "rebuild"})

    # 全新创建或重建
    if state.get("_collection"):
        try:
            state["_collection"].destroy()
        except Exception:
            pass
        state["_collection"] = None
    shutil.rmtree(persist_dir, ignore_errors=True)

    # rmtree 可能因文件锁定失败，强制逐文件清理
    if os.path.exists(persist_dir):
        for root, dirs, files in os.walk(persist_dir, topdown=False):
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), 0o777)
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except Exception:
                    pass
        try:
            os.rmdir(persist_dir)
        except Exception:
            pass

    # 如果仍无法清理，尝试直接 zvec.open（可能虽损坏但可打开），
    # 或使用备用目录名避免文件锁定问题
    attempt_dir = persist_dir
    if os.path.exists(attempt_dir):
        try:
            state["_collection"] = zvec.open(path=attempt_dir)
            _load_text_store(state)
            return
        except Exception:
            pass
        # 回退到备用目录，递增 v2/v3/... 直到找到可用的
        base = str(persist_dir)
        for suffix_num in range(2, 20):
            alt = f"{base}_v{suffix_num}"
            if os.path.exists(alt):
                try:
                    state["_collection"] = zvec.open(path=alt)
                    _load_text_store(state)
                    state["persist_dir"] = alt
                    return
                except Exception:
                    shutil.rmtree(alt, ignore_errors=True)
            if not os.path.exists(alt):
                attempt_dir = alt
                break
        else:
            raise RuntimeError(
                f"无法创建向量库目录 (v2~v19 均被占用): {base}。"
                f"请手动清理 tech_bureau_zvec* 目录后重试。"
            )

    state["_collection"] = zvec.create_and_open(
        path=attempt_dir,
        schema=zvec.CollectionSchema(
            name=state["collection_name"],
            vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, DIM)
        )
    )
    # 如果用了备用目录，更新 persist_dir
    if attempt_dir != str(persist_dir):
        state["persist_dir"] = attempt_dir
    _load_text_store(state)
    if state["_text_store"]:
        _restore_vectors(state)


def rebuild_store(state: dict) -> None:
    """销毁旧库，准备全量重新索引"""
    if not HAS_ZVEC:
        return
    persist_dir = state["persist_dir"]
    if state.get("_collection"):
        try:
            state["_collection"].destroy()
        except Exception:
            pass
        state["_collection"] = None
    state["_text_store"] = {}
    shutil.rmtree(persist_dir, ignore_errors=True)
    state["_collection"] = zvec.create_and_open(
        path=persist_dir,
        schema=zvec.CollectionSchema(
            name=state["collection_name"],
            vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, DIM)
        )
    )

    if state.get("_on_debug"):
        state["_on_debug"]("vector_store", "rebuild", {})
    if state.get("_log"):
        state["_log"]("vector_store", "INFO", "store rebuilt")


# ============================================================
# 状态操作 - 写入
# ============================================================

def add_chunks(state: dict, chunks: List[Dict]) -> None:
    """增量追加文档切片"""
    if not chunks or state.get("_collection") is None:
        return

    emb_client = state["_emb_client"]
    embedding_model = state["embedding_model"]
    collection = state["_collection"]
    total = len(chunks)

    for start in range(0, total, WRITE_BATCH):
        batch = chunks[start:start + WRITE_BATCH]
        texts = [c["text"] for c in batch]
        vectors = _embed(emb_client, embedding_model, texts)
        docs = []
        for i, c in enumerate(batch):
            doc_id = c["id"]
            docs.append(zvec.Doc(id=doc_id, vectors={"embedding": vectors[i]}))
            state["_text_store"][doc_id] = {
                "text": c["text"],
                "source": c.get("source", ""),
                "chunk_index": c.get("chunk_index", 0)
            }
        collection.insert(docs)
        collection.flush()
        batch_no = start // WRITE_BATCH + 1
        if state.get("_log"):
            state["_log"]("vector_store", "INFO",
                          f"batch {batch_no}/{((total + WRITE_BATCH - 1) // WRITE_BATCH)} ({len(batch)} chunks)")

    _save_text_store(state)


def add_faq_entry(state: dict, faq_id: str, question: str, answer: str) -> None:
    """增量写入一条 FAQ (自动截断过长文本以适配 Embedding 模型 token 限制)"""
    safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', faq_id)
    # bge-large-zh-v1.5 最大 512 token, 约 1500 中文字符, 保留安全余量
    max_chars = 1200
    answer_truncated = answer[:max_chars]
    text = f"Q: {question}\nA: {answer_truncated}"
    try:
        vec = _embed(state["_emb_client"], state["embedding_model"], [text])[0]
        state["_collection"].insert([
            zvec.Doc(id=safe_id, vectors={"embedding": vec})
        ])
        state["_collection"].flush()
        state["_text_store"][safe_id] = {"text": text, "source": "faq", "chunk_index": 0}
        _save_text_store(state)
    except Exception as e:
        if state.get("_on_debug"):
            state["_on_debug"]("vector_store", "add_faq_error", {"faq_id": faq_id, "error": str(e)})
        if state.get("_log"):
            state["_log"]("vector_store", "ERROR", f"add_faq failed: {faq_id} - {e}")


def remove_faq_entry(state: dict, faq_id: str) -> None:
    """从向量库删除一条 FAQ"""
    try:
        state["_collection"].delete(ids=[faq_id])
        state["_collection"].flush()
    except Exception:
        pass
    state["_text_store"].pop(faq_id, None)
    _save_text_store(state)


def index_docs_index(state: dict, cards: List[dict]) -> int:
    """将 docs_index 卡片写入 ZVec 向量库

    每个卡片作为独立 chunk，id 前缀 card_ 与原文档切片区分。
    返回写入数量。
    """
    if not cards:
        return 0

    collection = state["_collection"]
    if not collection:
        return 0

    emb_client = state["_emb_client"]
    embedding_model = state["embedding_model"]
    total = len(cards)
    written = 0

    for start in range(0, total, WRITE_BATCH):
        batch = cards[start:start + WRITE_BATCH]
        texts = [c["text"] for c in batch]
        vectors = _embed(emb_client, embedding_model, texts)
        docs = []
        for i, c in enumerate(batch):
            doc_id = c["id"]
            docs.append(zvec.Doc(id=doc_id, vectors={"embedding": vectors[i]}))
            state["_text_store"][doc_id] = {
                "text": c["text"],
                "source": c["source"],
                "chunk_index": 0
            }
            written += 1
        collection.insert(docs)
        collection.flush()

    _save_text_store(state)
    if state.get("_log"):
        state["_log"]("vector_store", "INFO", f"indexed {written} docs_index cards")
    return written


# ============================================================
# 状态操作 - 查询
# ============================================================

import time as _time_mod

def search_vectors(state: dict, query: str, top_k: int = 5) -> List[Dict]:
    """向量语义搜索"""
    _open_or_create(state)
    collection = state.get("_collection")
    if not collection:
        return []
    try:
        t0 = _time_mod.time()
        vec = _embed(state["_emb_client"], state["embedding_model"], [query])[0]
        emb_ms = round((_time_mod.time() - t0) * 1000)
        print(f"      [VectorStore] Embedding API → {emb_ms}ms")

        t1 = _time_mod.time()
        results = collection.query(
            zvec.VectorQuery("embedding", vector=vec), topk=top_k
        )
        q_ms = round((_time_mod.time() - t1) * 1000)
        print(f"      [VectorStore] ZVec query → {len(results)} results in {q_ms}ms")

        return [
            {"content": state["_text_store"].get(r.id, {}).get("text", ""),
             "source": state["_text_store"].get(r.id, {}).get("source", ""),
             "score": r.score, "id": r.id,
             "chunk_index": state["_text_store"].get(r.id, {}).get("chunk_index", 0)}
            for r in results
        ]
    except Exception as e:
        if state.get("_on_debug"):
            state["_on_debug"]("vector_store", "search_error", {"error": str(e)})
        return []


def keyword_search(state: dict, query: str, top_k: int = 5) -> List[Dict]:
    """关键词全文检索 (无需 Embedding)"""
    _open_or_create(state)

    t0 = _time_mod.time()
    total_docs = len(state["_text_store"])

    # 提取关键词
    keywords = []
    for part in query.replace(" ", " ").split():
        part = part.strip()
        if not part:
            continue
        if any('\u4e00' <= c <= '\u9fff' for c in part):
            for i in range(len(part) - 1):
                keywords.append(part[i:i + 2])
            keywords.append(part)
        else:
            keywords.append(part.lower())

    matches = []
    for doc_id, meta in state["_text_store"].items():
        text = meta.get("text", "").lower()
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            matches.append({
                "content": meta["text"],
                "source": meta.get("source", ""),
                "score": float(score),
                "id": doc_id,
                "chunk_index": meta.get("chunk_index", 0)
            })

    matches.sort(key=lambda x: x["score"], reverse=True)
    ms = round((_time_mod.time() - t0) * 1000)
    print(f"      [VectorStore] keyword scan {total_docs} docs → {len(matches[:top_k])} results in {ms}ms")
    return matches[:top_k]


def delete_by_source(state: dict, source: str) -> int:
    """删除指定来源的所有向量条目（zvec + text_store），返回删除数量"""
    ids_to_delete = []
    for doc_id, meta in list(state["_text_store"].items()):
        if meta.get("source", "") == source:
            ids_to_delete.append(doc_id)

    if not ids_to_delete:
        return 0

    # 1. 从 zvec 集合中删除向量
    if state.get("_collection"):
        try:
            state["_collection"].delete(ids=ids_to_delete)
            state["_collection"].flush()
            # 重建索引，确保已删除的向量从搜索索引中清除
            state["_collection"].optimize()
            print(f"    [VectorStore] zvec deleted {len(ids_to_delete)} ids for source: {source}")
        except Exception as e:
            print(f"    [VectorStore] WARN: zvec delete failed for {source}: {e}")

    # 2. 从 text_store 中删除文本（无论 zvec 是否成功都要清理）
    for doc_id in ids_to_delete:
        state["_text_store"].pop(doc_id, None)

    # 3. 持久化
    _save_text_store(state)
    print(f"    [VectorStore] text_store removed {len(ids_to_delete)} entries, remaining: {len(state['_text_store'])}")
    return len(ids_to_delete)


def list_entries(state: dict, source_filter: str = None) -> List[Dict]:
    """列出向量库中的所有条目，可按 source 过滤"""
    entries = []
    for doc_id, meta in state["_text_store"].items():
        src = meta.get("source", "")
        if source_filter and source_filter not in src:
            continue
        entries.append({
            "id": doc_id,
            "source": src,
            "text_preview": meta.get("text", "")[:100],
            "chunk_index": meta.get("chunk_index", 0),
        })
    entries.sort(key=lambda e: (e["source"], e["chunk_index"]))
    return entries


def delete_entry(state: dict, doc_id: str) -> bool:
    """删除单条向量条目"""
    if doc_id not in state["_text_store"]:
        return False

    # 从 zvec 删除
    if state.get("_collection"):
        try:
            state["_collection"].delete(ids=[doc_id])
            state["_collection"].flush()
        except Exception as e:
            print(f"    [VectorStore] zvec delete_entry failed for {doc_id}: {e}")

    # 从 text_store 删除
    state["_text_store"].pop(doc_id, None)
    _save_text_store(state)
    return True


def count_docs(state: dict) -> int:
    if HAS_ZVEC and state.get("_collection"):
        try:
            return state["_collection"].stats.row_count
        except Exception:
            pass
    return len(state.get("_text_store", {}))


# ============================================================
# 持久化辅助
# ============================================================

def _save_text_store(state: dict) -> None:
    try:
        text_store_path = state["_text_store_path"]
        os.makedirs(os.path.dirname(text_store_path), exist_ok=True)
        with open(text_store_path, "w", encoding="utf-8") as f:
            json.dump(state["_text_store"], f, ensure_ascii=False)
    except Exception as e:
        if state.get("_on_debug"):
            state["_on_debug"]("vector_store", "save_error", {"error": str(e)})


def _load_text_store(state: dict) -> None:
    text_store_path = state["_text_store_path"]
    if os.path.exists(text_store_path):
        try:
            with open(text_store_path, "r", encoding="utf-8") as f:
                state["_text_store"] = json.load(f)
        except Exception:
            state["_text_store"] = {}


def _restore_vectors(state: dict) -> None:
    items = list(state["_text_store"].items())
    emb_client = state["_emb_client"]
    embedding_model = state["embedding_model"]
    collection = state["_collection"]
    import time as _t

    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        ids = [id_ for id_, _ in batch]
        texts = [meta["text"] for _, meta in batch]
        try:
            vecs = _embed(emb_client, embedding_model, texts)
        except Exception:
            # 速率限制或其他错误 → 跳过此批次, 下次查询时按需恢复
            if i + BATCH_SIZE < len(items):
                _t.sleep(5)
            continue
        collection.insert([
            zvec.Doc(id=ids[j], vectors={"embedding": vecs[j]})
            for j in range(len(batch))
        ])
        if i + BATCH_SIZE < len(items):
            _t.sleep(1)
    collection.flush()


# ============================================================
# 工厂
# ============================================================

def create_vector_store(persist_dir, *,
                        emb_api_key: str,
                        emb_base_url: str,
                        embedding_model: str,
                        collection_name: str = "tech_bureau_docs",
                        on_debug: DebugCallback = None,
                        log: LogCallback = None) -> SimpleNamespace:
    """创建向量存储模块

    Args:
        persist_dir: ZVec 持久化目录
        emb_api_key: Embedding API 密钥
        emb_base_url: Embedding API 地址
        embedding_model: Embedding 模型名
        collection_name: 集合名称
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - search(query, top_k) -> List[Dict]
          - keyword_search(query, top_k) -> List[Dict]
          - add_chunks(chunks): 批量添加切片
          - add_faq(faq_id, question, answer): 添加FAQ
          - remove_faq(faq_id): 删除FAQ
          - index_docs_index(cards): 索引文档骨架卡片
          - rebuild(): 重建空库
          - count() -> int
          - _state: 内部状态 (调试用)
    """
    persist_dir = str(persist_dir)
    text_store_path = os.path.join(os.path.dirname(persist_dir), "text_store.json")

    import httpx
    state = {
        "persist_dir": persist_dir,
        "collection_name": collection_name,
        "_collection": None,
        "_text_store": {},
        "_text_store_path": text_store_path,
        "_emb_client": OpenAI(
            api_key=emb_api_key,
            base_url=emb_base_url,
            timeout=httpx.Timeout(timeout=30.0, connect=10.0, read=20.0, write=10.0),
            max_retries=1
        ),
        "embedding_model": embedding_model,
        "_on_debug": on_debug,
        "_log": log,
    }

    # 初始化
    _open_or_create(state)

    return SimpleNamespace(
        search=lambda q, top_k=5: search_vectors(state, q, top_k),
        keyword_search=lambda q, top_k=5: keyword_search(state, q, top_k),
        add_chunks=lambda chunks: add_chunks(state, chunks),
        add_faq=lambda faq_id, question, answer: add_faq_entry(state, faq_id, question, answer),
        remove_faq=lambda fid: remove_faq_entry(state, fid),
        index_docs_index=lambda cards: index_docs_index(state, cards),
        delete_by_source=lambda src: delete_by_source(state, src),
        list_entries=lambda source_filter=None: list_entries(state, source_filter),
        delete_entry=lambda did: delete_entry(state, did),
        rebuild=lambda: rebuild_store(state),
        count=lambda: count_docs(state),
        # 扩展/调试接口
        _state=state,
    )
