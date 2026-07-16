"""启动 Web 服务 (Waitress 生产模式)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from waitress import serve
from app import app
import config

print(f"  AI Agent Web 服务")
print(f"  模型: {config.LLM_MODEL}  |  ZVec + bge-large-zh-v1.5")
print(f"  打开浏览器访问: http://localhost:{config.WEB_PORT}")
print("=" * 50)
serve(app, host=config.WEB_HOST, port=config.WEB_PORT)
