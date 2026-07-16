"""文档问答 Agent - 主入口

使用方式:
    python main.py                    # 交互模式
    python main.py ask "你的问题"      # 单次查询
    python main.py correct "旧知识" "新内容"  # 管理员纠错
    python main.py reload-skills      # 热重载技能
    python main.py audit              # 查看审计日志
    python main.py index              # 扫描索引所有文档
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.agent import create_agent


def interactive_mode(agent):
    print("=" * 50)
    print("  文档问答 Agent - 函数式双轨记忆架构")
    print("  输入 'exit' 退出, 'reload' 热重载技能")
    print("=" * 50)
    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not query:
            continue
        if query.lower() == "exit":
            break
        if query.lower() == "reload":
            agent.reload_skills()
            print("[系统] 技能文件已热重载。")
            continue
        answer = agent.ask(query)
        print(f"\n{answer}")


def main():
    agent = create_agent()

    if len(sys.argv) < 2:
        interactive_mode(agent)
        return

    command = sys.argv[1]

    if command == "ask":
        query = sys.argv[2] if len(sys.argv) > 2 else input("请输入问题: ")
        answer = agent.ask(query)
        print(answer)

    elif command == "correct":
        if len(sys.argv) < 4:
            print("用法: python main.py correct <关键词> <修正内容>")
            sys.exit(1)
        agent.correct(sys.argv[2], sys.argv[3])
        print(f"[系统] 已添加纠错条目: [{sys.argv[2]}]")

    elif command == "reload-skills":
        agent.reload_skills()
        print("[系统] 技能文件已热重载。")

    elif command == "audit":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        logs = agent.audit_report(limit=limit)
        for log in logs:
            print(f"[{log.get('timestamp', '')}] {log.get('action', '')}: {log.get('detail', {})}")

    elif command == "index":
        total = agent.index_source_documents()
        print(f"[系统] 源文件索引完成，共 {total} 个文本切片。")

    else:
        print(f"未知命令: {command}")
        print("可用命令: ask, correct, reload-skills, audit, index")
        sys.exit(1)


if __name__ == "__main__":
    main()
