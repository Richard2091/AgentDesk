"""本机结构化消息编解码。"""

import json
from typing import Any

MAX_ENVELOPE_BYTES = 256 * 1024


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """构造 JSON 对象并拒绝重复键。"""
    result: dict[str, Any] = {}
    # 重复字段可能改变签名或校验解释，必须在解析阶段拒绝
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 包含重复字段: {key}")
        result[key] = value
    return result


def encode_message(message: Any) -> str:
    """将消息编码为单行 JSON，并限制信封大小。"""
    # 使用紧凑 UTF-8 JSON，确保传输上限可重复执行
    encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("消息超过 256 KiB 上限")
    return encoded


def decode_message(line: str) -> dict[str, Any]:
    """解析单行 JSON 消息并拒绝重复字段。"""
    # 在解析前限制字节长度，防止超大消息消耗资源
    if not isinstance(line, str) or len(line.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("消息必须为不超过 256 KiB 的 UTF-8 文本")
    decoded = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(decoded, dict):
        raise ValueError("消息必须为 JSON 对象")
    return decoded
