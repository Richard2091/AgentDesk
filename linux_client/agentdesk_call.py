"""AgentDesk 跨平台 TCP 命令行客户端。

在 Linux 等平台上通过 shell 直接调用 Windows 上的 AgentDesk Executor。
仅依赖 Python 标准库与仓库内 shared 模块，不导入 windows_executor 目录。
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Mapping

# 支持在 linux_client 目录内直接以 python agentdesk_call.py 方式运行
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config import load_shared_secret
from shared.protocol import (
    MESSAGE_CAPABILITY_QUERY,
    MESSAGE_REQUEST_EXECUTE,
    MESSAGE_REQUEST_STATUS,
    TERMINAL_STATUSES,
    SessionBinding,
    build_envelope,
    validate_envelope,
)
from shared.transport import decode_message, encode_message


class MessageError(RuntimeError):
    """Executor 返回 message.error 时的协议级异常。"""

    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        """保存错误码、错误描述和可选细节，供调用方按错误码分支处理。"""
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class AgentDeskClient:
    """通过 TCP 单行 JSON 通道访问 AgentDesk Executor 的客户端。"""

    def __init__(self, host: str, port: int, *, binding: SessionBinding) -> None:
        """建立到指定 Executor 的 TCP 连接并保存会话绑定。"""
        self._binding = binding
        self._socket: socket.socket | None = None
        self._stream: Any = None
        self.last_response: dict[str, Any] | None = None
        self._socket = socket.create_connection((host, port))
        self._stream = self._socket.makefile("rwb")

    def _roundtrip(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """发送单行 JSON 请求，读取一行响应并校验会话签名。"""
        if self._stream is None:
            raise RuntimeError("客户端连接已关闭")
        self._stream.write(encode_message(envelope).encode("utf-8"))
        self._stream.flush()
        line = self._stream.readline()
        if not line:
            raise ConnectionError("Executor 未返回响应")
        response = decode_message(line.decode("utf-8"))
        validate_envelope(response, self._binding)
        self.last_response = response
        return response

    def capability(self) -> dict[str, Any]:
        """发送能力查询并返回执行器能力报告载荷。"""
        request = build_envelope(MESSAGE_CAPABILITY_QUERY, {}, self._binding)
        response = self._roundtrip(request)
        if response["message_type"] != "capability.report":
            raise RuntimeError(f"能力查询返回了意外消息类型: {response.get('message_type')}")
        return dict(response["payload"])

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        contract_version: str = "0.1.0",
        timeout_ms: int | None = None,
        poll_interval: float = 0.2,
        poll_timeout: float = 30.0,
    ) -> dict[str, Any]:
        """发送执行请求；长任务自动轮询状态直到终态或超过轮询时限。"""
        request_id = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "tool": tool,
            "contract_version": contract_version,
            "arguments": dict(arguments),
        }
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        request = build_envelope(MESSAGE_REQUEST_EXECUTE, payload, self._binding, request_id=request_id)
        response = self._roundtrip(request)
        message_type = response["message_type"]
        if message_type == "message.error":
            error = response["payload"]
            raise MessageError(
                str(error.get("code", "unknown")),
                str(error.get("message", "请求处理失败")),
                details=error.get("details"),
            )
        if message_type == "result.final":
            return dict(response["payload"])
        if message_type != "status.response":
            raise RuntimeError(f"执行请求返回了意外消息类型: {message_type}")
        status_payload = response["payload"]
        deadline = time.monotonic() + poll_timeout
        while status_payload.get("status") not in TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"轮询超时（{poll_timeout:g} 秒），请求 {request_id} 未到达终态")
            time.sleep(poll_interval)
            poll_request = build_envelope(
                MESSAGE_REQUEST_STATUS,
                {"target_request_id": request_id},
                self._binding,
                request_id=request_id,
            )
            poll_response = self._roundtrip(poll_request)
            poll_type = poll_response["message_type"]
            if poll_type == "message.error":
                error = poll_response["payload"]
                raise MessageError(
                    str(error.get("code", "unknown")),
                    str(error.get("message", "请求处理失败")),
                    details=error.get("details"),
                )
            if poll_type != "status.response":
                raise RuntimeError(f"状态轮询返回了意外消息类型: {poll_type}")
            status_payload = poll_response["payload"]
        return dict(status_payload)

    def close(self) -> None:
        """关闭底层 TCP 连接并释放资源。"""
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def __enter__(self) -> "AgentDeskClient":
        """返回客户端自身，支持 with 语句自动管理连接。"""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出 with 语句时关闭连接，不吞掉调用方异常。"""
        self.close()


def _build_binding(session_id: str, executor_id: str, subject: str) -> SessionBinding:
    """按命令行参数与会话默认值构造 HMAC 会话绑定。"""
    return SessionBinding(
        session_id=session_id,
        executor_id=executor_id,
        subject=subject,
        auth_method="hmac-sha256",
        key_id="local-dev",
        secret=load_shared_secret(),
    )


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器；公共连接参数可写在子命令之后。"""
    parser = argparse.ArgumentParser(
        prog="agentdesk_call",
        description="AgentDesk 跨平台命令行客户端",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", required=True, help="Windows Executor 主机地址")
    common.add_argument("--port", type=int, required=True, help="Windows Executor 端口")
    common.add_argument("--session-id", default="session-network", help="会话标识（默认：session-network）")
    common.add_argument("--executor-id", default="executor-local", help="执行器标识（默认：executor-local）")
    common.add_argument("--subject", default="control-layer", help="调用主体（默认：control-layer）")

    subparsers.add_parser("capability", parents=[common], help="查询执行器能力报告")

    call_parser = subparsers.add_parser("call", parents=[common], help="调用指定工具")
    call_parser.add_argument("--tool", required=True, help="工具名称，例如 windows.system.info")
    call_parser.add_argument("--args", default="{}", help="工具参数 JSON 对象（默认：{}）")
    call_parser.add_argument("--timeout-ms", type=int, default=None, help="工具执行超时毫秒数")
    call_parser.add_argument(
        "--raw",
        action="store_true",
        help="输出完整响应信封 JSON 而非仅 payload 字段",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行入口：解析参数、执行请求并按约定输出与返回退出码。"""
    parsed = _build_parser().parse_args(argv)

    arguments: dict[str, Any] = {}
    if parsed.command == "call":
        try:
            decoded_arguments = json.loads(parsed.args)
        except json.JSONDecodeError as exc:
            print(f"工具参数 JSON 解析失败: {exc}", file=sys.stderr)
            return 1
        if not isinstance(decoded_arguments, dict):
            print("工具参数必须是 JSON 对象", file=sys.stderr)
            return 1
        arguments = decoded_arguments

    client: AgentDeskClient | None = None
    try:
        binding = _build_binding(parsed.session_id, parsed.executor_id, parsed.subject)
        client = AgentDeskClient(parsed.host, parsed.port, binding=binding)
        if parsed.command == "capability":
            output: Any = client.capability()
        else:
            output = client.call(parsed.tool, arguments, timeout_ms=parsed.timeout_ms)
            if parsed.raw:
                if client.last_response is None:
                    raise RuntimeError("缺少响应信封")
                output = client.last_response
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    except MessageError as exc:
        print(f"协议错误 [{exc.code}]: {exc}", file=sys.stderr)
        return 1
    except (ConnectionError, OSError) as exc:
        print(f"连接异常: {exc}", file=sys.stderr)
        return 2
    except (RuntimeError, TimeoutError, ValueError) as exc:
        print(f"请求失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())