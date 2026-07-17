"""源文件清单维护器 - 函数式架构

扫描 source/ 发现新增/更新的文件，记录时间戳，同名文件视为版本更新。

工厂: create_source_manifest(source_dir, manifest_path, *, on_debug=None, log=None)
返回 SimpleNamespace 含: refresh, get_traceability, get_full_manifest, _state
"""

import re
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Optional
from datetime import datetime

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 纯函数
# ============================================================

def _format_mtime(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


def _scan_files(source_dir: Path) -> Dict[str, List[dict]]:
    """扫描所有文件，按文件名分组 (支持平铺和递归目录)"""
    result = {}
    paths = []
    if source_dir and source_dir.exists():
        paths.extend(sorted(source_dir.rglob("*")))
    for path in paths:
        if path.is_dir() or path.name.startswith(".") or path.name.startswith("__"):
            continue
        if path.suffix.lower() in (".py", ".pyc", ".json"):
            continue
        if path.name == "filename_map.json" or path.name.startswith("_"):
            continue
        # 用相对路径作为 key，确保 knowledge_base 递归文件不冲突
        try:
            name = str(path.relative_to(source_dir)).replace("\\", "/")
        except ValueError:
            name = path.name
        stat = path.stat()
        entry = {
            "path": str(path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "suffix": path.suffix.lower()
        }
        if name not in result:
            result[name] = []
        result[name].append(entry)
    return result


def _parse_manifest(manifest_path: Path) -> Dict[str, List[dict]]:
    """解析已有 manifest 文件"""
    if not manifest_path.exists():
        return {}
    text = manifest_path.read_text(encoding="utf-8")
    result = {}
    current_name = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current_name = line[3:].strip().lstrip("`").rstrip("`")
            result[current_name] = []
        elif current_name and line.startswith("- ") and "修改时间" in line:
            m = re.search(r'修改时间: ([\d\-: ]+).*大小: (\d+)', line)
            if m:
                result[current_name].append({
                    "mtime_str": m.group(1),
                    "size": int(m.group(2))
                })
    return result


def _diff(old_index: dict, new_files: dict) -> tuple:
    newly_added = []
    updated = []
    for name, entries in new_files.items():
        if name not in old_index:
            newly_added.append({"name": name, "mtime": entries[-1]["mtime"]})
        elif len(entries) > len(old_index.get(name, [])):
            updated.append({"name": name, "mtime": entries[-1]["mtime"]})
    return newly_added, updated


def _build_manifest(files: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 源文件清单",
        f"> 自动维护 | 最后扫描: {now}",
        f"> 目录: `source/`",
        "",
    ]
    for name in sorted(files.keys()):
        entries = files[name]
        lines.append(f"## `{name}`")
        lines.append(f"- 版本数: {len(entries)}")
        for i, e in enumerate(entries, 1):
            mtime = _format_mtime(e["mtime"])
            lines.append(f"- v{i}. 修改时间: {mtime}, 大小: {e['size']} 字节, 格式: {e['suffix']}")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 状态操作
# ============================================================

def refresh_manifest(state: dict) -> str:
    """扫描 source/ + knowledge_base/，更新 manifest，返回新增/变更摘要"""
    source_dir = state["source_dir"]
    kb_dir = state.get("knowledge_base_dir")
    manifest_path = state["manifest_path"]

    files = {}
    files.update(_scan_files(source_dir))
    if kb_dir and kb_dir.exists():
        kb_files = _scan_files(kb_dir)
        for k, v in kb_files.items():
            prefixed_key = f"kb/{k}"
            files[prefixed_key] = v

    old_index = _parse_manifest(manifest_path)
    new_entries, updated_entries = _diff(old_index, files)
    manifest_text = _build_manifest(files)
    manifest_path.write_text(manifest_text, encoding="utf-8")

    report = ""
    if new_entries:
        report += "**新增文件:**\n" + "\n".join(
            f"- `{entry['name']}` (首次发现 {_format_mtime(entry['mtime'])})"
            for entry in new_entries) + "\n\n"
    if updated_entries:
        report += "**更新文件 (同名):**\n" + "\n".join(
            f"- `{entry['name']}` (更新于 {_format_mtime(entry['mtime'])})"
            for entry in updated_entries) + "\n\n"
    if not new_entries and not updated_entries:
        report = "目录无变化。"

    if state.get("_on_debug"):
        state["_on_debug"]("source_manifest", "refresh",
                           {"new": len(new_entries), "updated": len(updated_entries)})
    if state.get("_log"):
        state["_log"]("manifest", "INFO", f"refreshed: +{len(new_entries)} ~{len(updated_entries)}")

    return report


def get_traceability(state: dict, filename: str) -> str:
    """获取某个文件的可追溯信息"""
    manifest_path = state["manifest_path"]
    index = _parse_manifest(manifest_path)
    if filename not in index:
        return f"[未找到 {filename} 的目录记录]"
    entries = index[filename]
    if len(entries) == 1:
        e = entries[0]
        return f"`{filename}`: 唯一版本，添加于 {e.get('mtime_str', '?')}, 大小 {e['size']} 字节"
    lines = [f"`{filename}` 共有 {len(entries)} 个版本:"]
    for i, e in enumerate(entries, 1):
        lines.append(f"  v{i}. 修改于 {e.get('mtime_str', '?')}, 大小 {e['size']} 字节")
    return "\n".join(lines)


def get_full_manifest(state: dict) -> str:
    manifest_path = state["manifest_path"]
    if manifest_path.exists():
        return manifest_path.read_text(encoding="utf-8")
    return "(源文件清单尚未生成)"


# ============================================================
# 工厂
# ============================================================

def create_source_manifest(source_dir: Path, manifest_path: Path, *,
                           knowledge_base_dir: Path = None,
                           on_debug: DebugCallback = None,
                           log: LogCallback = None) -> SimpleNamespace:
    """创建源文件清单管理模块

    Args:
        source_dir: 源文件目录
        manifest_path: 清单输出路径
        knowledge_base_dir: 结构化知识库目录 (递归扫描)
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - refresh() -> str: 刷新清单，返回摘要
          - get_traceability(filename) -> str: 文件可追溯信息
          - get_full_manifest() -> str: 完整清单文本
          - _state: 内部状态 (调试用)
    """
    state = {
        "source_dir": Path(source_dir),
        "knowledge_base_dir": Path(knowledge_base_dir) if knowledge_base_dir else None,
        "manifest_path": Path(manifest_path),
        "_on_debug": on_debug,
        "_log": log,
    }
    state["source_dir"].mkdir(parents=True, exist_ok=True)

    return SimpleNamespace(
        refresh=lambda: refresh_manifest(state),
        get_traceability=lambda filename: get_traceability(state, filename),
        get_full_manifest=lambda: get_full_manifest(state),
        # 扩展/调试接口
        _state=state,
    )
