"""共享协议定义及第二阶段运行时辅助方法。"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

# 第一阶段冻结的消息协议版本；后续不兼容变更必须提升主版本。
PROTOCOL_VERSION = "0.1"
MESSAGE_CAPABILITY_QUERY = "capability.query"
MESSAGE_CAPABILITY_REPORT = "capability.report"
MESSAGE_REQUEST_EXECUTE = "request.execute"
MESSAGE_RESULT_FINAL = "result.final"
MESSAGE_REQUEST_STATUS = "request.status"
MESSAGE_STATUS_RESPONSE = "status.response"
MESSAGE_REQUEST_CANCEL = "request.cancel"
MESSAGE_CANCEL_ACK = "cancel.ack"
MESSAGE_ERROR = "message.error"

ENVELOPE_FIELDS = {
    "protocol_version", "message_id", "message_type", "session_id", "executor_id",
    "request_id", "actor", "issued_at", "expires_at", "nonce", "payload", "signature",
}
TERMINAL_STATUSES = {
    "completed", "invalid_arguments", "permission_denied", "timeout", "cancelled", "internal_error",
    "failed", "rejected", "expired",
}


class ProtocolError(ValueError):
    """协议解析、认证或会话绑定失败。"""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    """将时间格式化为 RFC3339 UTC 字符串。"""
    # 统一为 UTC，保证跨平台比较结果稳定
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """解析 RFC3339 时间并拒绝无时区值。"""
    if not isinstance(value, str) or not value:
        raise ProtocolError("invalid_request", "时间字段必须为非空字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError("invalid_request", "时间字段不是有效的 RFC3339 值") from exc
    if parsed.tzinfo is None:
        raise ProtocolError("invalid_request", "时间字段必须包含时区")
    return parsed.astimezone(timezone.utc)


def canonicalize(value: Any) -> bytes:
    """使用确定性 JSON 编码对象。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signing_view(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """生成移除签名值后的信封视图。"""
    view = copy.deepcopy(dict(envelope))
    signature = view.get("signature")
    if isinstance(signature, dict):
        signature["value"] = ""
    return view


def business_fingerprint(tool: str, contract_version: str, arguments: Mapping[str, Any], timeout_ms: int | None) -> str:
    """生成请求幂等业务指纹。"""
    # 仅纳入影响执行语义的字段，避免消息编号改变指纹
    return hashlib.sha256(canonicalize({
        "tool": tool,
        "contract_version": contract_version,
        "arguments": arguments,
        "timeout_ms": timeout_ms,
    })).hexdigest()


@dataclass(frozen=True)
class SessionBinding:
    """已认证单会话的不可变身份绑定。"""

    session_id: str
    executor_id: str
    subject: str
    auth_method: str
    key_id: str
    secret: bytes


def build_envelope(
    message_type: str,
    payload: Mapping[str, Any],
    binding: SessionBinding,
    *,
    request_id: str | None = None,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    message_id: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """创建带开发期 HMAC 签名的完整业务信封。"""
    # 计算消息有效期并填充可信会话身份
    issued = issued_at or utc_now()
    expires = expires_at or (issued + timedelta(seconds=30))
    envelope: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": message_id or secrets.token_hex(16),
        "message_type": message_type,
        "session_id": binding.session_id,
        "executor_id": binding.executor_id,
        "actor": {"subject": binding.subject, "auth_method": binding.auth_method},
        "issued_at": format_timestamp(issued),
        "expires_at": format_timestamp(expires),
        "nonce": nonce or secrets.token_hex(16),
        "payload": dict(payload),
        "signature": {"algorithm": "hmac-sha256", "key_id": binding.key_id, "value": ""},
    }
    if request_id is not None:
        envelope["request_id"] = request_id
    # 签名覆盖除 signature.value 外的全部字段
    envelope["signature"]["value"] = hmac.new(binding.secret, canonicalize(_signing_view(envelope)), hashlib.sha256).hexdigest()
    return envelope


def validate_envelope(envelope: Mapping[str, Any], binding: SessionBinding | None = None, *, now: datetime | None = None) -> None:
    """严格校验信封字段、时间窗口、会话绑定和开发期签名。"""
    # 校验顶层类型和未知字段，避免兼容性绕过
    if not isinstance(envelope, Mapping):
        raise ProtocolError("invalid_request", "消息信封必须为对象")
    unknown = set(envelope) - ENVELOPE_FIELDS
    if unknown:
        raise ProtocolError("invalid_request", "消息包含未知字段", {"fields": sorted(unknown)})
    required = ENVELOPE_FIELDS - {"request_id"}
    missing = required - set(envelope)
    if missing:
        raise ProtocolError("invalid_request", "消息缺少必填字段", {"fields": sorted(missing)})
    if envelope["protocol_version"] != PROTOCOL_VERSION:
        raise ProtocolError("unsupported_protocol", "不支持的协议版本")
    if not isinstance(envelope["payload"], Mapping) or not isinstance(envelope["actor"], Mapping):
        raise ProtocolError("invalid_request", "载荷和调用身份必须为对象")
    if set(envelope["actor"]) != {"subject", "auth_method"}:
        raise ProtocolError("invalid_request", "调用身份字段不完整或包含未知字段")
    if not all(isinstance(envelope[field], str) and envelope[field] for field in ("message_id", "message_type", "session_id", "executor_id", "nonce")):
        raise ProtocolError("invalid_request", "信封标识字段必须为非空字符串")
    if "request_id" in envelope and (not isinstance(envelope["request_id"], str) or not envelope["request_id"]):
        raise ProtocolError("invalid_request", "request_id 必须为非空字符串")
    if len(envelope["nonce"]) < 16:
        raise ProtocolError("invalid_request", "随机数长度不足")
    if not isinstance(envelope["signature"], Mapping) or set(envelope["signature"]) != {"algorithm", "key_id", "value"}:
        raise ProtocolError("invalid_request", "签名字段不完整或包含未知字段")
    issued = parse_timestamp(envelope["issued_at"])
    expires = parse_timestamp(envelope["expires_at"])
    current = (now or utc_now()).astimezone(timezone.utc)
    if expires <= issued or expires - issued > timedelta(seconds=60):
        raise ProtocolError("invalid_request", "消息有效期不符合协议限制")
    if current < issued - timedelta(seconds=30) or current > expires + timedelta(seconds=30):
        raise ProtocolError("request_expired", "消息已过期或尚未生效")
    if binding is not None:
        # 校验连接绑定字段和可信调用身份
        if envelope["session_id"] != binding.session_id or envelope["executor_id"] != binding.executor_id:
            raise ProtocolError("authentication_failed", "消息与当前会话绑定不一致")
        if envelope["actor"] != {"subject": binding.subject, "auth_method": binding.auth_method}:
            raise ProtocolError("authentication_failed", "调用身份与会话绑定不一致")
        if envelope["signature"]["algorithm"] != "hmac-sha256" or envelope["signature"]["key_id"] != binding.key_id:
            raise ProtocolError("authentication_failed", "消息签名算法或密钥标识不受信任")
        expected = hmac.new(binding.secret, canonicalize(_signing_view(envelope)), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(envelope["signature"]["value"])):
            raise ProtocolError("authentication_failed", "消息签名校验失败")
