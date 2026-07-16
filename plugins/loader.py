"""插件加载器 - 函数式架构 + MCP 协议

每个插件是 plugins/{name}/ 目录，包含:
  plugin.json  → 元数据 (name, description, tools, version)
  main.py      → 纯函数入口 (tool_call(tool_name, args) -> dict)

支持 MCP 标准协议: tools/list, tools/call (JSON-RPC 2.0)

工厂: create_plugin_loader(plugins_dir, *, on_debug=None, log=None)
返回 SimpleNamespace 含: list_tools, call_tool, get_plugin_info, reload, _state
"""

import json
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Optional, Any

from interfaces.types import DebugCallback, LogCallback


# ============================================================
# 纯函数 - 加载
# ============================================================

def _load_plugin_manifest(plugin_dir: Path) -> Optional[dict]:
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_plugin_module(plugin_dir: Path, plugin_name: str):
    """动态加载插件的 main.py 模块"""
    main_file = plugin_dir / "main.py"
    if not main_file.exists():
        return None
    try:
        module_name = f"plugins.{plugin_name}.main"
        return importlib.import_module(module_name)
    except Exception:
        return None


def _reload_plugin_module(plugin_dir: Path, plugin_name: str):
    """热重载插件模块"""
    main_file = plugin_dir / "main.py"
    if not main_file.exists():
        return None
    try:
        module_name = f"plugins.{plugin_name}.main"
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)
    except Exception:
        return None


# ============================================================
# MCP 协议操作
# ============================================================

def mcp_list_tools(state: dict) -> List[dict]:
    """MCP tools/list: 返回所有插件提供的工具列表"""
    tools = []
    for name, info in state["_plugins"].items():
        manifest = info["manifest"]
        for tool in manifest.get("tools", []):
            tools.append({
                "name": f"{name}.{tool['name']}",
                "description": tool.get("description", ""),
                "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                "plugin": name,
                "enabled": info.get("enabled", True),
            })
    return tools


def mcp_call_tool(state: dict, tool_full_name: str, arguments: dict) -> dict:
    """MCP tools/call: 调用插件工具"""
    parts = tool_full_name.split(".", 1)
    if len(parts) != 2:
        return {"error": f"无效的工具名: {tool_full_name}"}

    plugin_name, tool_name = parts
    info = state["_plugins"].get(plugin_name)
    if not info:
        return {"error": f"插件不存在: {plugin_name}"}

    if not info.get("enabled", True):
        return {"error": f"插件已禁用: {plugin_name}"}

    module = info.get("module")
    if not module:
        return {"error": f"插件模块未加载: {plugin_name}"}

    if not hasattr(module, "tool_call"):
        return {"error": f"插件缺少 tool_call 函数: {plugin_name}"}

    try:
        result = module.tool_call(tool_name, arguments)
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    except Exception as e:
        return {"error": str(e)}


def get_plugin_info(state: dict, plugin_name: str) -> Optional[dict]:
    """获取单个插件信息"""
    info = state["_plugins"].get(plugin_name)
    if not info:
        return None
    manifest = info["manifest"]
    return {
        "name": plugin_name,
        "description": manifest.get("description", ""),
        "version": manifest.get("version", "1.0.0"),
        "tools": manifest.get("tools", []),
        "enabled": info.get("enabled", True),
    }


def list_plugins(state: dict) -> List[dict]:
    """列出所有插件"""
    return [get_plugin_info(state, name) for name in state["_plugins"]]


def reload_plugins(state: dict) -> dict:
    """热重载所有插件"""
    plugins_dir = state["plugins_dir"]
    old_plugins = dict(state["_plugins"])

    new_plugins = {}
    for item in sorted(plugins_dir.iterdir()):
        if not item.is_dir() or item.name.startswith(".") or item.name.startswith("_"):
            continue

        manifest = _load_plugin_manifest(item)
        if not manifest:
            continue

        module = _reload_plugin_module(item, item.name)
        info = {
            "manifest": manifest,
            "module": module,
            "enabled": old_plugins.get(item.name, {}).get("enabled", True),
        }
        new_plugins[item.name] = info

    state["_plugins"] = new_plugins

    if state.get("_log"):
        state["_log"]("plugin", "INFO", f"reloaded: {len(new_plugins)} plugins")

    total_tools = sum(len(info["manifest"].get("tools", [])) for info in new_plugins.values())
    return {"plugins": len(new_plugins), "tools": total_tools}


# ============================================================
# 工厂
# ============================================================

def create_plugin_loader(plugins_dir: Path, *,
                         on_debug: DebugCallback = None,
                         log: LogCallback = None) -> SimpleNamespace:
    """创建插件加载器

    Args:
        plugins_dir: 插件目录
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - mcp_list_tools() -> List[dict]: MCP 工具列表
          - mcp_call_tool(name, args) -> dict: MCP 工具调用
          - list_plugins() -> List[dict]: 插件清单
          - get_plugin_info(name) -> dict: 插件详情
          - reload() -> dict: 热重载
          - _state: 内部状态
    """
    plugins_dir = Path(plugins_dir)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "plugins_dir": plugins_dir,
        "_plugins": {},
        "_on_debug": on_debug,
        "_log": log,
    }

    # 初始化加载
    reload_plugins(state)

    return SimpleNamespace(
        mcp_list_tools=lambda: mcp_list_tools(state),
        mcp_call_tool=lambda name, args: mcp_call_tool(state, name, args),
        list_plugins=lambda: list_plugins(state),
        get_plugin_info=lambda name: get_plugin_info(state, name),
        reload=lambda: reload_plugins(state),
        _state=state,
    )
