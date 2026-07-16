"""文档统计插件 - 文本分析工具"""

import re
from collections import Counter


def tool_call(tool_name: str, arguments: dict) -> dict:
    if tool_name == "word_count":
        return _word_count(arguments.get("text", ""))
    elif tool_name == "extract_keywords":
        return _extract_keywords(arguments.get("text", ""), arguments.get("top_n", 10))
    elif tool_name == "text_summary":
        return _text_summary(arguments.get("text", ""))
    return {"error": f"未知工具: {tool_name}"}


def _word_count(text: str) -> dict:
    chars = len(text)
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    words = len(re.findall(r'[a-zA-Z]+', text))
    total_words = chinese_chars + words
    paragraphs = len([p for p in text.split("\n") if p.strip()])
    return {
        "chars": chars, "chinese_chars": chinese_chars,
        "english_words": words, "total_words": total_words,
        "paragraphs": paragraphs,
    }


# 停止词
STOP_WORDS = set("的了吗呢啊吧着在地得是和都也就要与及对不有会这没有我们什么可以因为所以但是".split())


def _extract_keywords(text: str, top_n: int = 10) -> dict:
    # 提取中文词 (2-4 字)
    words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
    filtered = [w for w in words if w not in STOP_WORDS]
    counter = Counter(filtered)
    return {"keywords": [{"word": w, "count": c} for w, c in counter.most_common(min(top_n, 30))]}


def _text_summary(text: str) -> dict:
    if len(text) <= 300:
        return {"summary": text, "method": "原文较短, 直接显示全文"}
    first = text[:120].strip()
    mid_pos = len(text) // 2
    mid = text[mid_pos:mid_pos + 120].strip()
    last = text[-120:].strip()
    return {"summary": f"{first}...\n...{mid}...\n...{last}", "method": "三段截取法"}
