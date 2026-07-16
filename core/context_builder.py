"""上下文组装器 - 函数式架构

纯函数模块，无需工厂。所有函数无副作用，可直接独立测试。
"""

from typing import List, Optional
from pathlib import Path

from interfaces.types import MemoryEntry, Skill


# ============================================================
# 纯函数 - Prompt 组装
# ============================================================

def build_context(schema: str,
                  query: str,
                  skill: Optional[Skill] = None,
                  memory_entries: Optional[List[MemoryEntry]] = None,
                  entity_context: str = "",
                  manifest_context: str = "",
                  history_context: str = "",
                   plan_context: str = "",
                   pdf_page_context: str = "") -> str:
    """组装最终注入 LLM 的完整上下文"""
    parts = []

    if schema:
        parts.append(f"【系统指令 - 必须严格遵守】\n{schema}")

    if plan_context:
        parts.append(plan_context)

    if skill:
        parts.append(_skill_prompt(skill))

    if history_context:
        parts.append(history_context)

    if manifest_context:
        parts.append(manifest_context)

    if entity_context:
        parts.append(f"【实体字典参考】\n{entity_context}")

    if memory_entries:
        sorted_entries = sorted(memory_entries, key=lambda e: e.priority)
        parts.append(_memory_prompt(sorted_entries))

    if pdf_page_context:
        parts.append(pdf_page_context)

    parts.append(f"【用户问题】\n{query}")

    return "\n\n---\n\n".join(parts)


def build_manifest_context(manifest_dir: Path) -> str:
    """读取源文件清单文本"""
    manifest_path = Path(manifest_dir) / "source_manifest.md"
    if not manifest_path.exists():
        return ""
    content = manifest_path.read_text(encoding="utf-8")[:3000]
    return (
        "【源文件清单 - 请根据此清单进行文件溯源】\n"
        "以下是 source/ 目录下的所有文件及其版本信息。回答时请引用文件的具体版本和时间戳。\n\n"
        f"{content}"
    )


# ============================================================
# 内部辅助
# ============================================================

def _skill_prompt(skill: Skill) -> str:
    lines = [f"【当前激活技能: {skill.name}】"]
    if skill.sop_steps:
        lines.append("执行步骤:")
        for i, step in enumerate(skill.sop_steps, 1):
            lines.append(f"  {i}. {step}")
    if skill.output_template:
        lines.append(f"\n输出格式要求:\n{skill.output_template}")
    return "\n".join(lines)


def _memory_prompt(entries: List[MemoryEntry]) -> str:
    lines = ["【检索到的知识条目】"]
    total_chars = 0
    MAX_MEMORY_CHARS = 6000
    used = set()
    for entry in entries:
        source_tag = f"[来源: {entry.source}]"
        block = f"\n{source_tag}\n{entry.content}"
        block_key = entry.source + entry.content[:80]
        if block_key in used:
            continue
        used.add(block_key)
        total_chars += len(block)
        if total_chars > MAX_MEMORY_CHARS and len(lines) > 1:
            lines.append(f"\n[... 共 {len(entries)} 条，已展示前 {len(lines)-1} 条 ...]")
            break
        lines.append(block)
    return "\n".join(lines)
