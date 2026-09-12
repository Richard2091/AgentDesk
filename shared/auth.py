"""本机消息认证基础能力。"""
import hashlib
import hmac
import json
import time


def _canonicalize(message):
    """按稳定字段顺序序列化消息。"""
    return json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_message(message, secret):
    """使用共享密钥生成消息签名。"""
    # 计算规范化消息的 HMAC 摘要
    return hmac.new(secret, _canonicalize(message), hashlib.sha256).hexdigest()


def verify_message(message, signature, secret, now=None, max_age_seconds=30):
    """校验消息签名、时间戳和随机数字段。"""
    # 校验必需字段，拒绝缺少认证上下文的消息
    if not message.get("session_id") or not message.get("nonce") or not isinstance(message.get("issued_at"), int):
        return False
    # 校验消息时间窗口，避免过期消息继续执行
    current = int(time.time()) if now is None else now
    if abs(current - message["issued_at"]) > max_age_seconds:
        return False
    # 校验消息完整性
    expected = sign_message(message, secret)
    return hmac.compare_digest(expected, signature)
