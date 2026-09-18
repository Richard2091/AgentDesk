"""Executor 本机认证消息入口。"""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping

from shared.config import load_shared_secret
from shared.errors import make_error
from shared.protocol import (
    MESSAGE_CAPABILITY_QUERY,
    MESSAGE_CAPABILITY_REPORT,
    MESSAGE_CANCEL_ACK,
    MESSAGE_ERROR,
    MESSAGE_REQUEST_CANCEL,
    MESSAGE_REQUEST_EXECUTE,
    MESSAGE_REQUEST_STATUS,
    MESSAGE_RESULT_FINAL,
    MESSAGE_STATUS_RESPONSE,
    ProtocolError,
    SessionBinding,
    build_envelope,
    validate_envelope,
)
from shared.replay import ReplayGuard
from shared.schema import validate_message_payload
from shared.transport import decode_message, encode_message
from windows_executor.main import ExecutorRuntime, build_capability_report


class ExecutorMessageServer:
    """校验单会话信封并将协议消息路由到执行器运行时。"""

    def __init__(self, binding: SessionBinding, runtime: ExecutorRuntime | None = None):
        self.binding = binding
        self.runtime = runtime or ExecutorRuntime(executor_id=binding.executor_id)
        self.replay_guard = ReplayGuard(ttl_seconds=360)

    def handle(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """处理一条认证消息并返回已签名响应信封。"""
        try:
            # 按字段、签名、绑定和时间顺序验证输入信封
            validate_envelope(envelope, self.binding)
            replay_key = f"{envelope['message_id']}:{envelope['nonce']}:{envelope['signature']['key_id']}"
            if not self.replay_guard.accept(self.binding.session_id, replay_key):
                raise ProtocolError("replay_detected", "检测到重复消息")
            # 根据消息类型执行对应请求流水线
            return self._dispatch(envelope)
        except ProtocolError as exc:
            return self._error_response(envelope, exc.code, exc.message, exc.details)
        except Exception:
            return self._error_response(envelope, "internal_error", "执行器内部错误")

    def close(self) -> None:
        """关闭消息服务并释放执行线程。"""
        # 清理执行器线程池，保证进程可以退出
        self.runtime.shutdown()

    def _dispatch(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """将已认证消息分派到能力、执行、状态或取消处理器。"""
        message_type = envelope["message_type"]
        payload = envelope["payload"]
        request_id = envelope.get("request_id")
        if message_type == MESSAGE_CAPABILITY_QUERY:
            if payload:
                raise ProtocolError("invalid_request", "能力查询载荷必须为空对象")
            self._validate_payload_schema(payload, "capabilityQuery")
            response = self.runtime.capability_report(in_reply_to=envelope["message_id"])
            return build_envelope(MESSAGE_CAPABILITY_REPORT, response, self.binding)
        if message_type == MESSAGE_REQUEST_EXECUTE:
            self._require_payload(payload, {"tool", "contract_version", "arguments"}, {"timeout_ms"})
            self._validate_payload_schema(payload, "requestExecute")
            if not request_id:
                raise ProtocolError("invalid_request", "执行请求缺少 request_id")
            record = self.runtime.submit(
                request_id, payload["tool"], payload["contract_version"], payload["arguments"],
                timeout_ms=payload.get("timeout_ms"), subject=envelope["actor"]["subject"],
            )
            result = self.runtime.result_for(record) if record.error and record.error.get("code") == "request_conflict" else self.runtime.status(request_id)
            if result["status"] in {"completed", "failed", "timeout", "cancelled"}:
                return build_envelope(MESSAGE_RESULT_FINAL, self._final_payload(result), self.binding, request_id=request_id)
            return build_envelope(MESSAGE_STATUS_RESPONSE, self._status_payload(result), self.binding, request_id=request_id)
        if message_type == MESSAGE_REQUEST_STATUS:
            self._require_payload(payload, {"target_request_id"}, set())
            self._validate_payload_schema(payload, "requestStatus")
            target = payload["target_request_id"]
            status = self.runtime.status(target)
            if status["error"] and status["error"]["code"] == "request_not_found":
                raise ProtocolError("request_not_found", "请求不存在")
            return build_envelope(MESSAGE_STATUS_RESPONSE, self._status_payload(status), self.binding, request_id=target)
        if message_type == MESSAGE_REQUEST_CANCEL:
            self._require_payload(payload, {"reason"}, set())
            self._validate_payload_schema(payload, "requestCancel")
            if not request_id:
                raise ProtocolError("invalid_request", "取消请求缺少 request_id")
            outcome = self.runtime.cancel(request_id)
            if outcome.get("outcome") == "not_found":
                raise ProtocolError("request_not_found", "请求不存在")
            ack = {"outcome": outcome["outcome"]}
            self._validate_payload_schema(ack, "cancelAck")
            return build_envelope(MESSAGE_CANCEL_ACK, ack, self.binding, request_id=request_id)
        raise ProtocolError("unsupported_message", "不支持的消息类型")

    @staticmethod
    def _require_payload(payload: Mapping[str, Any], required: set[str], optional: set[str]) -> None:
        """校验消息载荷必填字段并拒绝未知字段。"""
        # 按冻结契约拒绝缺失或未知字段
        if not isinstance(payload, Mapping):
            raise ProtocolError("invalid_request", "消息载荷必须为对象")
        missing = required - set(payload)
        unknown = set(payload) - required - optional
        if missing or unknown:
            raise ProtocolError("invalid_request", "消息载荷字段不符合契约", {"missing": sorted(missing), "unknown": sorted(unknown)})

    def _error_response(self, envelope: Mapping[str, Any], code: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """构造不泄露请求参数的协议错误响应。"""
        # 仅在可用时关联原消息编号，错误详情保持脱敏
        payload = {"in_reply_to": str(envelope.get("message_id", "unknown")), "error": make_error(code, message, details=details)}
        self._validate_payload_schema(payload, "messageError")
        return build_envelope(MESSAGE_ERROR, payload, self.binding)

    @staticmethod
    def _validate_payload_schema(payload: Mapping[str, Any], definition: str) -> None:
        """校验冻结消息载荷 Schema，并转换为协议错误。"""
        # 对请求与响应统一执行 Draft 2020-12 约束
        try:
            validate_message_payload(payload, definition)
        except Exception as exc:
            raise ProtocolError("invalid_request", "消息载荷不符合冻结 Schema", {"definition": definition}) from exc

    @staticmethod
    def _status_payload(result: Mapping[str, Any]) -> dict[str, Any]:
        """将内部请求记录转换为 status.response 允许的载荷。"""
        # 仅保留冻结状态载荷字段，避免泄露内部耗时字段
        status = "failed" if result["status"] == "internal_error" else result["status"]
        payload = {"request_id": result["request_id"], "status": status, "updated_at": result["updated_at"]}
        if status in {"completed", "failed", "timeout", "cancelled"}:
            payload["result"] = result["result"]
            payload["error"] = result["error"]
        validate_message_payload(payload, "statusResponse")
        return payload

    @staticmethod
    def _final_payload(result: Mapping[str, Any]) -> dict[str, Any]:
        """将内部请求记录转换为 result.final 允许的载荷。"""
        # 请求编号已位于信封顶层，载荷只携带终态字段
        payload = {"status": "failed" if result["status"] == "internal_error" else result["status"], "result": result["result"], "error": result["error"], "duration_ms": result["duration_ms"]}
        validate_message_payload(payload, "resultFinal")
        return payload


def _binding_from_environment() -> SessionBinding:
    """从开发期本机配置建立单会话绑定。"""
    # 本机传输通过受控进程环境完成会话引导
    return SessionBinding(
        session_id=os.environ.get("AGENTDESK_SESSION_ID", "session-local"),
        executor_id=os.environ.get("AGENTDESK_EXECUTOR_ID", "executor-local"),
        subject=os.environ.get("AGENTDESK_ACTOR_SUBJECT", "control-layer"),
        auth_method="hmac-sha256",
        key_id=os.environ.get("AGENTDESK_KEY_ID", "local-dev"),
        secret=load_shared_secret(),
    )


def main() -> None:
    """持续处理标准输入中的本机单行 JSON 消息。"""
    # Windows 管道默认可能使用系统代码页，协议固定要求 UTF-8
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    line = sys.stdin.readline()
    if not line:
        return
    message = decode_message(line)
    if set(message) <= {"message_type", "payload"} and message.get("message_type") == MESSAGE_CAPABILITY_QUERY:
        # 标准输入输出能力查询公开真实默认工具；执行请求仍必须使用认证信封
        report = build_capability_report(legacy=False)
        report.update({"protocol_version": "0.1", "executor_id": os.environ.get("AGENTDESK_EXECUTOR_ID", "executor-local")})
        print(encode_message(report), end="", flush=True)
        return
    server = ExecutorMessageServer(_binding_from_environment())
    try:
        # 保持同一认证会话，逐行处理能力、执行、状态和取消消息
        print(encode_message(server.handle(message)), end="", flush=True)
        for current_line in sys.stdin:
            if not current_line.strip():
                continue
            # 输出经过认证的协议响应信封
            current_message = decode_message(current_line)
            print(encode_message(server.handle(current_message)), end="", flush=True)
    finally:
        server.close()


if __name__ == "__main__":
    main()
