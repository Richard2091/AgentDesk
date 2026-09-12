"""本机结构化消息编解码。"""
import json

def encode_message(message):
    """将消息编码为单行 JSON。"""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"

def decode_message(line):
    """解析单行 JSON 消息。"""
    return json.loads(line)
