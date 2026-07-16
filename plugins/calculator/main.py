"""计算器插件 - 提供算术运算工具"""

import json


# ============================================================
# 工具定义 (MCP 兼容)
# ============================================================

# tool_call 纯函数: 无副作用, 无外部依赖
def tool_call(tool_name: str, arguments: dict) -> dict:
    """插件入口: 纯函数, 按 tool_name 路由"""
    if tool_name == "evaluate":
        return _evaluate(arguments.get("expression", ""))
    elif tool_name == "convert_unit":
        return _convert_unit(arguments.get("value", 0), arguments.get("from_unit", ""), arguments.get("to_unit", ""))
    return {"error": f"未知工具: {tool_name}"}


def _evaluate(expression: str) -> dict:
    """安全计算数学表达式"""
    if not expression or len(expression) > 200:
        return {"error": "表达式无效或过长"}
    # 白名单安全计算
    allowed = set("0123456789.+-*/()^% eExPiIntsqrQ")
    cleaned = "".join(c for c in expression if c in allowed or c.isspace())
    if cleaned != expression.strip():
        return {"error": "表达式包含非法字符"}
    try:
        # 使用 eval 的安全子集
        safe_globals = {"__builtins__": {}}
        safe_locals = {
            "pi": 3.141592653589793,
            "e": 2.718281828459045,
            "sqrt": lambda x: x ** 0.5,
            "abs": abs, "round": round,
            "min": min, "max": max,
            "pow": pow, "int": int, "float": float,
        }
        result = eval(cleaned, safe_globals, safe_locals)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": f"计算失败: {e}"}


# 单位换算表
_UNIT_CONVERSIONS = {
    "km_to_m": 1000, "m_to_cm": 100, "cm_to_mm": 10,
    "kg_to_g": 1000, "g_to_mg": 1000,
    "h_to_min": 60, "min_to_s": 60,
    "c_to_f": lambda c: c * 9/5 + 32,
    "f_to_c": lambda f: (f - 32) * 5/9,
}


def _convert_unit(value, from_unit: str, to_unit: str) -> dict:
    """简单单位换算"""
    key = f"{from_unit}_to_{to_unit}"
    conv = _UNIT_CONVERSIONS.get(key)
    if conv is None:
        return {"error": f"不支持 {from_unit} 到 {to_unit} 的换算"}
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"error": "value 必须是数字"}
    result = conv(v) if callable(conv) else v * conv
    return {"value": value, "from": from_unit, "to": to_unit, "result": result}
