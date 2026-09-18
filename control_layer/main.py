import json
import os
import subprocess
import sys
from pathlib import Path
from shared.config import load_shared_secret

def discover_executor():
    """启动执行器并发现其能力。"""
    # 启动执行器子进程并注入项目根目录
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(root))
    result = subprocess.run([sys.executable, str(root / "windows_executor" / "main.py")], capture_output=True, text=True, check=True, env=env)
    # 解析执行器返回的结构化能力
    return json.loads(result.stdout)

def main():
    """执行最小注册与能力发现流程。"""
    # 校验开发期本机通道配置，缺少共享密钥时拒绝启动。
    load_shared_secret()
    # 查询执行器能力并输出结果
    print(json.dumps(discover_executor(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
