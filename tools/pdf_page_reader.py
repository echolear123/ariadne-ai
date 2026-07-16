"""PDF 页面读取工具 - 函数式架构

工厂: create_pdf_reader(source_dir, *, on_debug=None, log=None)
返回 SimpleNamespace 含: extract, extract_formatted, extract_smart, _state
"""

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from pypdf import PdfReader

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 纯函数
# ============================================================

def _resolve_file(source_dir: Path, filename: str, kb_dir: Path = None) -> Optional[Path]:
    """精确匹配 → kb递归匹配 → 模糊匹配 → None"""
    exact = source_dir / filename
    if exact.exists():
        return exact

    # 递归搜索 knowledge_base
    if kb_dir and kb_dir.exists():
        for f in kb_dir.rglob(filename):
            return f
        for f in kb_dir.rglob(f"*{filename}*"):
            return f

    # 文件名包含子串
    candidates = []
    for f in source_dir.glob("*.pdf"):
        clean_f = f.name.lower().replace('.pdf', '')
        clean_q = filename.lower().replace('.pdf', '')
        if clean_q in clean_f:
            candidates.append(f)
    if candidates:
        return candidates[0]

    # 关键词模糊匹配
    kw_chars = re.findall(r'[\u4e00-\u9fff\w]+', filename)
    for f in source_dir.glob("*.pdf"):
        if all(k in f.name for k in kw_chars if len(k) >= 2):
            return f
    return None


def extract_pdf(source_dir: Path, filename: str, start_page: int, end_page: int,
                kb_dir: Path = None) -> dict:
    """提取指定文件页面，返回 dict (纯函数)"""
    filepath = _resolve_file(source_dir, filename, kb_dir)
    if not filepath:
        return {"ok": False, "error": f"未找到匹配文件: {filename}"}

    if start_page < 0:
        start_page = 0
    if end_page - start_page > 50:
        end_page = start_page + 50

    try:
        reader = PdfReader(str(filepath))
        total = len(reader.pages)
        actual_start = max(0, min(start_page, total - 1))
        actual_end = min(end_page, total)
        parts = []
        for i in range(actual_start, actual_end):
            try:
                t = reader.pages[i].extract_text()
                if t:
                    parts.append(f"=== 第 {i+1} 页 ===\n{t}")
            except Exception:
                pass
        text = "\n\n".join(parts)
        if text.strip():
            return {"ok": True, "total_pages": total,
                    "extracted": f"{actual_start+1}-{actual_end}", "text": text}
        else:
            return {"ok": False, "error": "无可提取文本 (可能是扫描件)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def extract_formatted(source_dir: Path, filename: str, start_page: int, end_page: int,
                      max_chars: int = 4000, kb_dir: Path = None) -> str:
    """提取并格式化为 Markdown 文本 (纯函数)"""
    data = extract_pdf(source_dir, filename, start_page, end_page, kb_dir=kb_dir)

    if not data.get("ok"):
        return f"[PDF 提取失败: {data.get('error', '未知错误')}]"

    text = data["text"]
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n...(内容截断, 共 {len(data['text'])} 字符)"

    return (
        f"【从 {filename} 提取 (第 {data.get('extracted', '?')} 页 "
        f"/ 共 {data.get('total_pages', '?')} 页)】\n\n{text}"
    )


def extract_smart(source_dir: Path, filename: str, query: str, max_chars: int = 4000) -> str:
    """智能提取: 根据查询关键词决定提取范围 (纯函数)"""
    chapter_match = re.search(r'第\s*([一二三四五六七八九十\d]+)\s*[章节]', query)
    if chapter_match:
        num_str = chapter_match.group(1)
        cn_map = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
                  '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
        num = int(cn_map.get(num_str, num_str))
        start = (num - 1) * 20
        end = start + 40
        return extract_formatted(source_dir, filename, start, end, max_chars)

    if re.search(r'总结|结论|结尾|end|conclusion', query, re.IGNORECASE):
        return extract_formatted(source_dir, filename, 200, 999999, max_chars)

    if re.search(r'目录|前言|概述|概要', query):
        return extract_formatted(source_dir, filename, 0, 10, max_chars)

    return extract_formatted(source_dir, filename, 0, 40, max_chars)


# ============================================================
# 工厂
# ============================================================

def create_pdf_reader(source_dir: Path, *,
                      knowledge_base_dir: Path = None,
                      on_debug: DebugCallback = None,
                      log: LogCallback = None) -> SimpleNamespace:
    """创建 PDF 页面读取工具

    Args:
        source_dir: PDF 文件目录
        knowledge_base_dir: 结构化知识库目录 (递归搜索)
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - extract(filename, start, end) -> dict
          - extract_formatted(filename, start, end, max_chars) -> str
          - extract_smart(filename, query, max_chars) -> str
          - _state: 内部状态 (调试用)
    """
    src = Path(source_dir)
    kb = Path(knowledge_base_dir) if knowledge_base_dir else None

    def _logged_formatted(filename, start, end, max_chars=4000):
        result = extract_formatted(src, filename, start, end, max_chars, kb_dir=kb)
        if state.get("_on_debug"):
            state["_on_debug"]("pdf_reader", "extract_formatted",
                               {"filename": filename, "pages": f"{start}-{end}"})
        if state.get("_log"):
            state["_log"]("pdf_extract", "INFO",
                          f"extracted {filename} pages {start}-{end}")
        return result

    def _logged_smart(filename, query, max_chars=4000):
        result = extract_smart(src, filename, query, max_chars)
        if state.get("_on_debug"):
            state["_on_debug"]("pdf_reader", "extract_smart",
                               {"filename": filename, "query": query})
        return result

    state = {
        "source_dir": src,
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        extract=lambda filename, start, end: extract_pdf(src, filename, start, end),
        extract_formatted=_logged_formatted,
        extract_smart=_logged_smart,
        # 扩展/调试接口
        _state=state,
    )
