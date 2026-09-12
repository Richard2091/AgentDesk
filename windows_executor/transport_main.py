"""Executor 本机消息入口。"""
import sys
from shared.protocol import MESSAGE_CAPABILITY_QUERY
from shared.transport import decode_message, encode_message
from windows_executor.main import build_capability_report

def main():
    """处理一条能力查询并返回能力报告。"""
    # 读取控制层发送的结构化消息
    line = sys.stdin.readline()
    message = decode_message(line)
    # 校验消息类型并返回能力报告
    if message.get("message_type") != MESSAGE_CAPABILITY_QUERY:
        raise ValueError("不支持的消息类型")
    print(encode_message(build_capability_report()), end="", flush=True)

if __name__ == "__main__":
    main()
