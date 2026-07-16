"""后台审查 - 函数式架构

自进化 FAQ 评分/聚类/淘汰。
依赖注入 LLM client, auditor, fast_memory, long_memory。

工厂: create_reviewer(llm_client, auditor, fast_memory, long_memory=None, schema="", *, on_debug, log)
返回 SimpleNamespace 含: review, _state
"""

import re
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional, Dict, List
from pathlib import Path

from interfaces.types import DebugCallback, LogCallback, ReviewResult
import config


# ============================================================
# 常量
# ============================================================

MAX_FAQ_ITEMS = 200
EVICT_THRESHOLD = 2
EVICT_AGE_DAYS = 14
SCORE_THRESHOLD = 6
CLUSTER_SIMILARITY = 0.7

CHITCHAT_PATTERNS = [
    r'^(你好|hi|hello|hey|嗨|谢谢|thank|再见|bye|ok|好的|嗯|哦)\b',
]

SENSITIVE_PATTERNS = [
    (r'(王|李|张|刘|陈|杨|赵|黄|周|吴|徐|孙|马|朱|胡|郭|何|高|林)\w{1,2}(?=[，。；、\s])', '[相关人员]'),
    (r'1[3-9]\d{9}', '[手机号]'),
    (r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]', '[身份证号]'),
]


# ============================================================
# 纯函数 - 检测
# ============================================================

def _is_chitchat(query: str) -> bool:
    q = query.strip().lower()
    if len(q) <= 3:
        return True
    for pat in CHITCHAT_PATTERNS:
        if re.match(pat, q):
            return True
    return False


def _detect_sensitive(text: str) -> bool:
    for pat, _ in SENSITIVE_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _desensitize(text: str) -> str:
    for pat, repl in SENSITIVE_PATTERNS:
        text = re.sub(pat, repl, text)
    return text


# ============================================================
# LLM 评分和聚类
# ============================================================

def _score_with_llm(llm_client, query: str, answer: str) -> dict:
    """调用 LLM 评估问答质量和保留价值"""
    if not llm_client:
        return {"quality": 3 if len(answer) > 50 else 1,
                "value": 3 if len(answer) > 100 else 1}

    prompt = (
        "评估以下问答的质量和保留价值。\n\n"
        f"问题: {query}\n\n"
        f"回答: {answer[:500]}\n\n"
        "请以 JSON 格式返回评分，不要输出其他内容:\n"
        '{"quality": 1-5, "value": 1-5}\n'
        "其中 quality 是回答准确性和完整度，value 是问题本身的长期参考价值。\n"
        "日常闲聊、嘘寒问暖的 value 应为 1。\n"
        "专业术语解释、产品参数、算法原理等有长期参考价值的 value 应为 4-5。"
    )
    try:
        resp = llm_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=100
        )
        text = resp.choices[0].message.content.strip()
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            data = json.loads(json_match.group())
            return {"quality": data.get("quality", 3), "value": data.get("value", 3)}
    except Exception:
        pass
    return {"quality": 3, "value": 3}


def _find_cluster(llm_client, fast_memory, new_query: str) -> Optional[str]:
    """用 LLM 判断新问题与已有 FAQ 是否为同类问题"""
    faq_file = Path(fast_memory._state["base_dir"]) / "public_faq.md"
    if not faq_file.exists():
        return None

    content = faq_file.read_text(encoding="utf-8")
    existing_questions = re.findall(r'^## Q:\s*(.+)$', content, re.MULTILINE)
    if not existing_questions:
        return None

    candidates = existing_questions[-20:]

    prompt = (
        "判断以下新问题是否与已有问题属于同一类问题。\n\n"
        f"新问题: {new_query}\n\n"
        "已有问题列表:\n" + "\n".join(f"- {q}" for q in candidates) + "\n\n"
        "判断标准:\n"
        "1. 先看专业领域是否相同 (如都是YOLO算法、都是某款硬件参数)\n"
        "2. 讨论的内容是否一致 (如都在问性能参数、都在问安装方法)\n"
        "3. 主语指代是否一样 (如都在问同一款产品)\n\n"
        "以 JSON 返回: {\"similar_to\": \"匹配到的已有问题(完全一致时)\" 或 null, "
        "\"reason\": \"简短说明\"}\n"
        "只有高度相似(领域+内容+主语都相同)才返回匹配。"
    )
    try:
        resp = llm_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=200
        )
        text = resp.choices[0].message.content.strip()
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("similar_to")
    except Exception:
        pass
    return None


# ============================================================
# FAQ 写入和淘汰
# ============================================================

def _write_faq(fast_memory, query: str, answer: str, score: int,
               cluster: Optional[str], state: dict) -> str:
    """写入 public_faq.md"""
    faq_file = Path(fast_memory._state["base_dir"]) / "public_faq.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    faq_id = f"faq_{int(datetime.now().timestamp())}"

    if cluster:
        content = faq_file.read_text(encoding="utf-8")
        pattern = rf'(## \[{re.escape(cluster)}\].*?\n)'
        marker = (f"<!-- score:{score} | created:{now} | last_hit:{now} -->\n"
                  f"## Q: {query}\n## A:\n{answer}\n\n")
        if re.search(pattern, content, re.DOTALL):
            lines = content.split("\n")
            new_lines = []
            in_cluster = False
            for line in lines:
                new_lines.append(line)
                if line.startswith(f"## [{cluster}]"):
                    in_cluster = True
                elif in_cluster and line.startswith("## [") and not line.startswith(f"## [{cluster}]"):
                    new_lines.insert(-1, marker)
                    in_cluster = False
            if in_cluster:
                new_lines.append(marker)
            faq_file.write_text("\n".join(new_lines), encoding="utf-8")
        else:
            with open(faq_file, "a", encoding="utf-8") as f:
                f.write(f"\n## [{cluster}]\n{marker}")
    else:
        entry = (
            f"\n<!-- score:{score} | created:{now} | last_hit:{now} -->\n"
            f"## [{query}]\n## Q: {query}\n## A:\n{answer}\n"
        )
        with open(faq_file, "a", encoding="utf-8") as f:
            f.write(entry)

    _maybe_evict(fast_memory, state)
    return faq_id


def _maybe_evict(fast_memory, state: dict) -> None:
    """当 FAQ 超过上限时淘汰低分条目"""
    faq_file = Path(fast_memory._state["base_dir"]) / "public_faq.md"
    if not faq_file.exists():
        return

    content = faq_file.read_text(encoding="utf-8")
    entries = re.findall(
        r'<!-- score:(\d+).*?created:(\d{4}-\d{2}-\d{2}).*?last_hit:(\d{4}-\d{2}-\d{2}).*?-->\n(## Q:.*?\n## A:.*?)(?=\n<!--|\n## \[|\Z)',
        content, re.DOTALL
    )

    if len(entries) <= MAX_FAQ_ITEMS:
        return

    now = datetime.now()
    scored_entries = []
    for score_str, created_str, last_hit_str, block in entries:
        score = int(score_str)
        try:
            created = datetime.strptime(created_str, "%Y-%m-%d %H:%M")
            age_days = (now - created).days
            score -= max(0, age_days // 7)
        except ValueError:
            pass
        scored_entries.append((score, block))

    scored_entries.sort(key=lambda x: x[0])
    to_remove = len(entries) - MAX_FAQ_ITEMS + 20
    to_remove = max(to_remove, 0)

    to_remove_blocks = set(block for score, block in scored_entries[:to_remove]
                           if score <= EVICT_THRESHOLD)
    if not to_remove_blocks:
        return

    new_content = content
    for block in to_remove_blocks:
        new_content = new_content.replace(block, "")
    new_content = re.sub(r'\n{3,}', '\n\n', new_content)
    faq_file.write_text(new_content.strip() + "\n", encoding="utf-8")

    # 同步删除 ZVec
    long_memory = state.get("long_memory")
    if long_memory:
        for block in to_remove_blocks:
            q_match = re.search(r'## Q:\s*(.+?)\n', block)
            if q_match:
                faq_id = f"faq_{hash(q_match.group(1)) % 100000}"
                try:
                    long_memory.vector_store.remove_faq(faq_id)
                except Exception:
                    pass

    if state.get("_log"):
        state["_log"]("faq_evict", "INFO",
                      f"evicted {len(to_remove_blocks)} items, remaining {len(entries) - len(to_remove_blocks)}")


# ============================================================
# 主审查函数
# ============================================================

def review_answer(state: dict, query: str, answer: str, meta: dict = None) -> Dict:
    """审查一次问答，返回评估结果"""
    auditor = state["auditor"]
    llm_client = state["llm_client"]
    fast_memory = state["fast_memory"]

    # 1. 闲聊过滤
    if _is_chitchat(query):
        auditor.log_action("review_skip", {"query": query, "reason": "chitchat"})
        return {"scores": {"accuracy": 0, "completeness": 0},
                "total": 0, "deposited": False, "skipped": True}

    # 2. LLM 评分
    scores = _score_with_llm(llm_client, query, answer)
    total = scores.get("quality", 0) + scores.get("value", 0)
    has_sensitive = _detect_sensitive(answer)

    auditor.log_action("review", {"query": query, "scores": scores,
                                   "total": total, "has_sensitive": has_sensitive})

    if state.get("_on_debug"):
        state["_on_debug"]("reviewer", "review",
                           {"query": query[:50], "total": total, "sensitive": has_sensitive})

    # 3. 低于阈值不写入
    if total < SCORE_THRESHOLD or has_sensitive:
        return {"scores": scores, "total": total, "deposited": False}

    # 4. 脱敏
    answer_clean = _desensitize(answer)

    # 5. LLM 聚类
    cluster_group = _find_cluster(llm_client, fast_memory, query)

    # 6. 写入 FAQ
    faq_id = _write_faq(fast_memory, query, answer_clean, total, cluster_group, state)

    # 7. 写入 ZVec
    long_memory = state.get("long_memory")
    if long_memory:
        long_memory.vector_store.add_faq(
            faq_id=f"faq_{faq_id}",
            question=query,
            answer=answer_clean
        )

    auditor.log_action("faq_written", {"query": query, "score": total,
                                         "cluster": cluster_group or "new"})
    return {"scores": scores, "total": total, "deposited": True,
            "cluster": cluster_group}


# ============================================================
# 工厂
# ============================================================

def create_reviewer(llm_client,
                    auditor,
                    fast_memory,
                    long_memory=None,
                    schema: str = "",
                    *,
                    on_debug: DebugCallback = None,
                    log: LogCallback = None) -> SimpleNamespace:
    """创建后台审查模块

    Args:
        llm_client: OpenAI 客户端实例
        auditor: create_audit_logger 返回的审计模块
        fast_memory: create_fast_memory 返回的快记忆模块
        long_memory: create_long_memory 返回的长记忆模块 (可选)
        schema: 系统指令 (保留)
        on_debug: 调试回调
        log: 日志回调

    Returns:
        SimpleNamespace with:
          - review(query, answer, meta) -> dict: 审查问答
          - _state: 内部状态 (调试用)
    """
    state = {
        "llm_client": llm_client,
        "auditor": auditor,
        "fast_memory": fast_memory,
        "long_memory": long_memory,
        "schema": schema,
        "_on_debug": on_debug,
        "_log": log,
    }

    return SimpleNamespace(
        review=lambda q, a, meta=None: review_answer(state, q, a, meta),
        # 扩展/调试接口
        _state=state,
    )
