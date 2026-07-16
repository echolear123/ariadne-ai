"""文档读取器 - 函数式架构

流程: 文档解析(pypdf/docx/纯文本) → 切片(Chunking) → 返回 chunks

工厂: create_doc_reader(source_dir, docs_index_dir, *, on_debug=None, log=None)
返回 SimpleNamespace 含: scan_to_chunks, _state
"""

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Tuple
from datetime import datetime

from pypdf import PdfReader

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 常量
# ============================================================

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


# ============================================================
# 纯函数 - 文件名安全 ID
# ============================================================

def _make_safe_id(filename: str) -> str:
    """生成 ZVec 兼容的 short_id (≤55 字符，ASCII only)"""
    if filename.isascii():
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', filename)
        if len(safe) > 55:
            safe = f"{safe[:50]}_{abs(hash(filename)) % 10000:04d}"
        return safe

    md5_prefix = hashlib.md5(filename.encode('utf-8')).hexdigest()[:12]
    suffix = Path(filename).suffix.lstrip('.')
    safe_suffix = re.sub(r'[^a-zA-Z0-9]', '', suffix)[:8]
    return f"d_{md5_prefix}_{safe_suffix}" if safe_suffix else f"d_{md5_prefix}"


# ============================================================
# 纯函数 - 文档解析
# ============================================================

def _extract_pdf(path: Path) -> Tuple[str, int]:
    """用 pypdf 提取 PDF 全文"""
    reader = PdfReader(str(path))
    total = len(reader.pages)
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text()
            if t:
                parts.append(t)
        except Exception:
            pass
    text = "\n\n".join(parts)
    return text, total


def _extract_docx(path: Path) -> str:
    if not HAS_DOCX:
        return ""
    try:
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def _extract(filepath: Path) -> Tuple[str, int]:
    """提取文档全文文本"""
    suffix = filepath.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(filepath)
    elif suffix == ".docx":
        return _extract_docx(filepath), 0
    elif suffix in (".txt", ".md"):
        return filepath.read_text(encoding="utf-8", errors="replace"), 0
    return "", 0


def _chunk(text: str, filename: str) -> List[Dict]:
    """滑动窗口切片"""
    safe = _make_safe_id(filename)
    chunks, i, start = [], 0, 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append({
            "id": f"{safe}_c{i}",
            "text": text[start:end],
            "source": filename,
            "chunk_index": i
        })
        i += 1
        start = end - CHUNK_OVERLAP if end < len(text) else end
    return chunks


# ============================================================
# 纯函数 - 卡片
# ============================================================

def _headings(text: str) -> str:
    lines = []
    for l in text.split("\n"):
        l = l.strip()
        if l and len(l) <= 80:
            lines.append(f"- {l}")
    return "\n".join(lines[:50]) if lines else "(未检测到标准目录结构)"


def _write_card(docs_index_dir: Path, filepath: Path, text: str,
                total_pages: int = 0, source_name: str = None):
    if source_name is None:
        source_name = filepath.name
    # card 文件名: 用 source_name 替换路径分隔符避免文件系统冲突
    base = source_name.replace("/", "_").replace("\\", "_")
    # 去掉原始扩展名避免双重后缀
    if base.endswith(".md") or base.endswith(".pdf") or base.endswith(".docx"):
        base = base.rsplit(".", 1)[0]
    card_name = base + ".md"
    p = docs_index_dir / card_name
    s = text[:200].replace("\n", " ").strip()
    h = _headings(text)
    t = datetime.now().strftime("%Y-%m-%d")
    short_id = _make_safe_id(source_name)
    pages_info = f"| 页数 | {total_pages} |\n" if total_pages > 0 else ""
    content = (
        f"# {source_name}\n\n"
        f"## 基本信息\n\n"
        f"| 属性 | 值 |\n|------|-----|\n"
        f"| 文件名 | {source_name} |\n"
        f"| short_id | {short_id} |\n"
        f"| 格式 | {filepath.suffix} |\n"
        f"| 索引日期 | {t} |\n"
        f"| 文件大小 | {filepath.stat().st_size} 字节 |\n"
        f"{pages_info}"
        f"## 摘要\n\n{s}...\n\n"
        f"## 目录结构\n\n{h}\n"
    )
    if p.exists():
        old = p.read_text(encoding="utf-8")
        if "short_id" in old:
            return
    p.write_text(content, encoding="utf-8")


def _add_cross_links(docs_index_dir: Path):
    """扫描所有卡片文件，基于关键词重叠自动生成 [[双向链接]]"""
    cards = list(docs_index_dir.glob("*.md"))
    if len(cards) < 2:
        return

    card_data = {}
    for card in cards:
        text = card.read_text(encoding="utf-8")[:800]
        name = card.stem
        words = set(re.findall(r'[\u4e00-\u9fff\w]{2,}', text.lower()))
        card_data[name] = {"path": card, "words": words}

    names = list(card_data.keys())
    links = {n: [] for n in names}
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i >= j:
                continue
            overlap = card_data[a]["words"] & card_data[b]["words"]
            a_clean = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', a.lower())
            b_clean = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', b.lower())
            if len(overlap) >= 3 and a_clean != b_clean:
                links[a].append(b)
                links[b].append(a)

    for name, linked in links.items():
        if not linked:
            continue
        card_path = card_data[name]["path"]
        content = card_path.read_text(encoding="utf-8")
        if "## 相关文档" in content:
            continue
        link_lines = "\n".join(f"- {ln}" for ln in sorted(linked)[:10])
        content += f"\n\n## 相关文档\n\n{link_lines}\n"
        card_path.write_text(content, encoding="utf-8")


# ============================================================
# 状态操作
# ============================================================

def scan_to_chunks(state: dict) -> List[Dict]:
    """扫描 source/ + knowledge_base/ 目录，提取所有文档文本并切片"""
    source_dir = state["source_dir"]
    kb_dir = state.get("knowledge_base_dir")
    docs_index_dir = state["docs_index_dir"]
    filename_map = state["_filename_map"]
    all_chunks = []

    # 收集所有待处理文件: (source_name, filepath)
    # source_name 用于标识来源: 平铺文件直接用文件名, 递归文件用相对路径
    files_to_process = []

    if source_dir and source_dir.exists():
        for f in sorted(source_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED and not f.name.startswith("."):
                files_to_process.append((f.name, f))

    if kb_dir and kb_dir.exists():
        for f in sorted(kb_dir.rglob("*")):
            if f.is_file() and f.suffix.lower() in SUPPORTED and not f.name.startswith("."):
                # 跳过 index.md 和 _开头文件
                if f.name == "index.md":
                    continue
                rel = f.relative_to(kb_dir)
                source_name = str(rel).replace("\\", "/")  # e.g. "部门/details/xxx.md"
                files_to_process.append((source_name, f))

    for source_name, filepath in files_to_process:
        if state.get("_log"):
            state["_log"]("doc_index", "INFO", f"processing: {source_name}")

        try:
            text, total_pages = _extract(filepath)
        except Exception as e:
            if state.get("_on_debug"):
                state["_on_debug"]("doc_reader", "extract_error",
                                   {"file": source_name, "error": str(e)})
            continue

        if not text or len(text.strip()) < 10:
            continue

        # 清理 PDF 中可能存在的无效 Unicode 代理字符
        text = text.encode('utf-8', errors='replace').decode('utf-8')

        try:
            _write_card(docs_index_dir, filepath, text, total_pages=total_pages,
                        source_name=source_name)
            chunks = _chunk(text, source_name)
            all_chunks.extend(chunks)

            safe = _make_safe_id(source_name)
            filename_map[source_name] = safe

            if state.get("_log"):
                total_tag = f"{total_pages}p, " if total_pages > 0 else ""
                state["_log"]("doc_index", "INFO",
                              f"done: {source_name} -> {total_tag}{len(chunks)} chunks")
        except Exception as e:
            if state.get("_on_debug"):
                state["_on_debug"]("doc_reader", "write_error",
                                   {"file": source_name, "error": str(e)})

    # 保存 filename_map
    _save_filename_map(state)
    # 生成 Wiki 双链接
    _add_cross_links(docs_index_dir)

    if state.get("_on_debug"):
        state["_on_debug"]("doc_reader", "scan_done", {"total_chunks": len(all_chunks)})

    return all_chunks


def _load_filename_map(state: dict) -> Dict[str, str]:
    map_path = state["_filename_map_path"]
    if map_path.exists():
        try:
            return json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_filename_map(state: dict):
    try:
        state["_filename_map_path"].write_text(
            json.dumps(state["_filename_map"], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


def _process_single_file(state: dict, filepath: Path, source_name: str = None) -> Tuple[List[Dict], dict]:
    """处理单个文件: 提取文本 → 切片 → 写卡片, 返回 (chunks, card_dict)"""
    docs_index_dir = state["docs_index_dir"]

    if source_name is None:
        source_name = filepath.name

    text, total_pages = _extract(filepath)
    if not text or len(text.strip()) < 10:
        return [], None

    # 清理 PDF 中可能存在的无效 Unicode 代理字符 (如 emoji 残留)
    text = text.encode('utf-8', errors='replace').decode('utf-8')

    _write_card(docs_index_dir, filepath, text, total_pages=total_pages,
                source_name=source_name)
    chunks = _chunk(text, source_name)

    safe = _make_safe_id(source_name)
    state["_filename_map"][source_name] = safe
    _save_filename_map(state)

    # 生成卡片字典（与 vector_store.index_docs_index 兼容）
    import hashlib
    card_base = source_name.replace("/", "_").replace("\\", "_")
    if card_base.endswith(".md") or card_base.endswith(".pdf") or card_base.endswith(".docx"):
        card_base = card_base.rsplit(".", 1)[0]
    card_name = card_base + ".md"
    card_id = "card_" + hashlib.md5(card_name.encode()).hexdigest()[:16]
    card_dict = {
        "id": card_id,
        "text": text[:400],
        "source": f"docs_index/{card_name}",
    }

    return chunks, card_dict


# ============================================================
# 工厂
# ============================================================

def create_doc_reader(source_dir: Path, docs_index_dir: Path, *,
                      knowledge_base_dir: Path = None,
                      on_debug: DebugCallback = None,
                      log: LogCallback = None) -> SimpleNamespace:
    """创建文档读取模块

    Args:
        source_dir: 源文件目录
        docs_index_dir: 骨架卡片输出目录
        knowledge_base_dir: 结构化知识库目录 (递归扫描)
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - scan_to_chunks() -> List[Dict]: 扫描并返回所有切片
          - process_single_file(filepath, source_name) -> (chunks, card): 处理单个文件
          - _state: 内部状态 (调试用)
    """
    docs_index_dir = Path(docs_index_dir)
    docs_index_dir.mkdir(parents=True, exist_ok=True)
    filename_map_path = docs_index_dir / "filename_map.json"

    state = {
        "source_dir": Path(source_dir),
        "knowledge_base_dir": Path(knowledge_base_dir) if knowledge_base_dir else None,
        "docs_index_dir": docs_index_dir,
        "_filename_map_path": filename_map_path,
        "_filename_map": {},
        "_on_debug": on_debug,
        "_log": log,
    }
    # 加载已有映射
    state["_filename_map"] = _load_filename_map(state)

    return SimpleNamespace(
        scan_to_chunks=lambda: scan_to_chunks(state),
        process_single_file=lambda fp, sn=None: _process_single_file(state, Path(fp), sn),
        # 扩展/调试接口
        _state=state,
    )
