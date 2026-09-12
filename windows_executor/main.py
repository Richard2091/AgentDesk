"""Windows Executor 最小骨架。"""
import json
import platform
import uuid
from shared.protocol import PROTOCOL_VERSION

def build_capability_report():
    """构造执行器能力报告。"""
    # 查询当前执行器基础运行环境
    return {
        "protocol_version": PROTOCOL_VERSION,
        "executor_id": "executor-" + uuid.uuid4().hex[:12],
        "executor_version": "0.1.0",
        "os_version": platform.platform(),
        "supported_protocol_versions": [PROTOCOL_VERSION],
        "supported_messages": ["capability.query", "capability.report"],
        "capability_epoch": uuid.uuid4().hex,
        "tools": [],
    }

def main():
    """启动执行器并输出能力报告。"""
    # 生成并输出结构化能力信息
    print(json.dumps(build_capability_report(), ensure_ascii=False))

if __name__ == "__main__":
    main()
