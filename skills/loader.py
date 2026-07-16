"""技能加载器 - 函数式架构

解析 fast_memory/skills/*.md 文件，每个 MD 包含四个标准段落:
  # 技能元数据
  # 触发条件
  # 执行思维链
  # 输出格式

工厂: create_skill_loader(skills_dir, *, on_debug=None, log=None)
返回 SimpleNamespace 含: match, get_all, reload, _state
"""

import re
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

from interfaces.types import Skill, DebugCallback, LogCallback


# ============================================================
# 纯函数 - 解析
# ============================================================

SECTION_KEYS = {
    "技能元数据": "metadata_section",
    "触发条件": "triggers_section",
    "执行思维链": "sop_section",
    "输出格式": "output_section",
}


def _split_sections(content: str) -> dict:
    """按 # 标题拆分为段落字典"""
    sections = {}
    pattern = r'^#\s+(.+?)$'
    parts = re.split(pattern, content, flags=re.MULTILINE)
    if not parts:
        return sections
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[title] = body
    return sections


def _extract_name(section: str) -> str:
    m = re.search(r'技能名称[：:]\s*(.+)', section)
    return m.group(1).strip() if m else ""


def _extract_triggers(section: str) -> List[str]:
    triggers = []
    for m in re.finditer(r'[「「"\"](.+?)[」」"\"]', section):
        triggers.append(m.group(1))
    return triggers


def _extract_list(section: str) -> List[str]:
    items = re.findall(r'\d+\.\s*(.+?)(?=\n\d+\.|\Z)', section, re.DOTALL)
    return [item.strip() for item in items]


def _extract_entity_refs(sop_section: str) -> List[str]:
    return re.findall(r'entities/(\w+)\.md', sop_section)


def _parse_skill_file(filepath: Path) -> Optional[Skill]:
    """解析单个 Skill MD 文件 (纯函数)"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    sections = _split_sections(content)
    name = _extract_name(sections.get("技能元数据", ""))
    description = sections.get("技能元数据", "")
    triggers = _extract_triggers(sections.get("触发条件", ""))
    sop_steps = _extract_list(sections.get("执行思维链", ""))
    output_template = sections.get("输出格式", "").strip()
    entity_refs = _extract_entity_refs(sections.get("执行思维链", ""))

    if not name or not triggers:
        return None

    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        sop_steps=sop_steps,
        output_template=output_template,
        entity_refs=entity_refs,
        metadata={"file": str(filepath)}
    )


# ============================================================
# 状态操作函数
# ============================================================

def reload_skills(state: dict) -> None:
    """热重载: 重新扫描所有 Skill MD 文件"""
    state["_skills"].clear()
    skills_dir = state["skills_dir"]
    if not skills_dir.exists():
        return
    for md_file in skills_dir.glob("*.md"):
        skill = _parse_skill_file(md_file)
        if skill:
            state["_skills"].append(skill)

    if state.get("_on_debug"):
        state["_on_debug"]("skill_loader", "reload", {"count": len(state["_skills"])})
    if state.get("_log"):
        state["_log"]("reload", "INFO", f"skills reloaded: {len(state['_skills'])}")


def match_skill(state: dict, query: str) -> Optional[Skill]:
    """触发条件匹配: 查询包含任一触发词则命中"""
    for skill in state["_skills"]:
        for trigger in skill.triggers:
            if trigger in query:
                return skill
    return None


def get_all_skills(state: dict) -> List[Skill]:
    return list(state["_skills"])


# ============================================================
# 工厂
# ============================================================

def create_skill_loader(skills_dir: Path, *,
                        on_debug: DebugCallback = None,
                        log: LogCallback = None) -> SimpleNamespace:
    """创建技能加载模块

    Args:
        skills_dir: Skill MD 文件目录
        on_debug: 调试回调 (module, action, detail)
        log: 日志回调 (action, level, detail_str)

    Returns:
        SimpleNamespace with:
          - match(query) -> Skill|None: 匹配技能
          - get_all() -> List[Skill]: 所有技能
          - reload(): 热重载
          - _state: 内部状态 (调试用)
    """
    state = {
        "skills_dir": Path(skills_dir),
        "_skills": [],
        "_on_debug": on_debug,
        "_log": log,
    }
    # 初始加载
    reload_skills(state)

    return SimpleNamespace(
        match=lambda query: match_skill(state, query),
        get_all=lambda: get_all_skills(state),
        reload=lambda: reload_skills(state),
        # 扩展/调试接口
        _state=state,
    )
