"""第二阶段统一错误对象。"""

from __future__ import annotations

from typing import Any, Mapping


def make_error(code: str, message: str, *, retryable: bool = False, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """构造符合冻结协议的脱敏错误对象。"""
    # 统一错误字段，调用方只依赖机器可判定的 code
    return {"code": code, "message": message, "retryable": retryable, "details": dict(details or {})}


ERROR_MESSAGES = {
    "invalid_arguments": "工具参数校验失败",
    "permission_denied": "当前身份无权调用该工具",
    "timeout": "工具执行超时",
    "cancelled": "工具执行已取消",
    "internal_error": "执行器内部错误",
    "unsupported_tool": "工具不存在或版本不匹配",
    "request_not_found": "请求不存在",
}


def error_for(code: str, *, retryable: bool = False, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """按错误码生成默认中文错误。"""
    # 使用固定中文文案，避免把异常原文泄露给调用方
    return make_error(code, ERROR_MESSAGES.get(code, "请求处理失败"), retryable=retryable, details=details)
