"""控制层会话、能力发现和执行请求客户端。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from shared.config import load_shared_secret
from shared.protocol import (
    MESSAGE_CAPABILITY_QUERY,
    MESSAGE_REQUEST_CANCEL,
    MESSAGE_REQUEST_EXECUTE,
    MESSAGE_REQUEST_STATUS,
    SessionBinding,
    build_envelope,
    validate_envelope,
)
from shared.schema import validate_envelope_schema
from shared.session import SessionRegistry
from shared.transport import decode_message, encode_message
from windows_executor.main import ExecutorRuntime
from windows_executor.transport_main import ExecutorMessageServer


class ControlLayerService:
    """单 Executor、单会话的控制层运行时服务。"""

    def __init__(self, *, secret: bytes | None = None, executor_id: str = "executor-local", subject: str = "control-layer", runtime: ExecutorRuntime | None = None, use_subprocess: bool = False):
        """初始化控制层会话，可选择进程内或真实 Executor 子进程通道。"""
        # 创建单执行器会话绑定；子进程模式将绑定字段注入受控环境
        self.registry = SessionRegistry(secret or load_shared_secret(), executor_id, subject=subject)
        self.binding: SessionBinding = self.registry.register()
        self._process: subprocess.Popen[str] | None = None
        if use_subprocess:
            if runtime is not None:
                raise ValueError("子进程模式不能同时传入进程内运行时")
            self.runtime = None
            self.server = None
            self._process = self._start_executor_process()
        else:
            self.runtime = runtime or ExecutorRuntime(executor_id=executor_id)
            self.server = ExecutorMessageServer(self.binding, self.runtime)

    def _start_executor_process(self) -> subprocess.Popen[str]:
        """启动并绑定一个真实 Executor 标准输入输出子进程。"""
        # 仅向子进程注入当前会话必要字段，不把密钥写入消息或日志
        root = Path(__file__).resolve().parent.parent
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(root) + os.pathsep + environment.get("PYTHONPATH", "")
        environment["AGENTDESK_SHARED_SECRET"] = self.binding.secret.decode("utf-8")
        environment["AGENTDESK_SESSION_ID"] = self.binding.session_id
        environment["AGENTDESK_EXECUTOR_ID"] = self.binding.executor_id
        environment["AGENTDESK_ACTOR_SUBJECT"] = self.binding.subject
        environment["AGENTDESK_KEY_ID"] = self.binding.key_id
        environment["PYTHONIOENCODING"] = "utf-8"
        return subprocess.Popen(
            [sys.executable, str(root / "windows_executor" / "transport_main.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=environment,
        )

    def _handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """通过当前传输模式发送一条消息并读取响应。"""
        # 进程内模式直接路由；子进程模式使用单行 JSON 通道
        if self._process is None:
            assert self.server is not None
            return self.server.handle(request)
        if self._process.stdin is None or self._process.stdout is None or self._process.poll() is not None:
            raise RuntimeError("Executor 子进程不可用")
        self._process.stdin.write(encode_message(request))
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("Executor 未返回消息")
        return decode_message(line)

    def capability(self) -> dict[str, Any]:
        """发送能力查询并校验执行器能力报告。"""
        # 构造认证信封并在本地服务端完成一次请求往返
        request = build_envelope(MESSAGE_CAPABILITY_QUERY, {}, self.binding)
        validate_envelope_schema(request)
        response = self._handle(request)
        validate_envelope(response, self.binding)
        if response["message_type"] != "capability.report":
            raise RuntimeError("能力查询未返回能力报告")
        return response["payload"]

    def execute(self, tool: str, arguments: Mapping[str, Any], *, contract_version: str = "0.1.0", timeout_ms: int | None = None, request_id: str | None = None) -> dict[str, Any]:
        """发送执行请求并返回结构化终态结果。"""
        # 生成请求编号和符合协议的执行载荷
        import uuid
        target_request_id = request_id or "request-" + uuid.uuid4().hex
        payload: dict[str, Any] = {"tool": tool, "contract_version": contract_version, "arguments": dict(arguments)}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        request = build_envelope(MESSAGE_REQUEST_EXECUTE, payload, self.binding, request_id=target_request_id)
        response = self._handle(request)
        validate_envelope(response, self.binding)
        payload = response["payload"]
        if response["message_type"] == "result.final":
            if payload.get("error") and payload["error"].get("code") == "request_conflict":
                # 冲突响应不能重新查询并覆盖原请求的真实状态
                return {"request_id": target_request_id, **payload}
            # 统一首次执行与幂等重试的可观测字段，避免消息类型差异泄露给调用方
            result = self.status(target_request_id)
            result.pop("updated_at", None)
            return result
        # 长任务先返回执行中状态，再轮询到唯一终态
        deadline = time.monotonic() + ((timeout_ms or 60000) / 1000) + 1
        while time.monotonic() < deadline:
            status = self.status(target_request_id)
            if status.get("status") in {"completed", "failed", "timeout", "cancelled"}:
                status.pop("updated_at", None)
                return status
            time.sleep(0.01)
        return self.status(target_request_id)

    def submit(self, tool: str, arguments: Mapping[str, Any], *, contract_version: str = "0.1.0", timeout_ms: int | None = None, request_id: str | None = None) -> dict[str, Any]:
        """提交异步执行请求并返回当前状态，供取消和状态查询流程使用。"""
        # 构造请求信封并只返回 Executor 当前状态
        import uuid
        target_request_id = request_id or "request-" + uuid.uuid4().hex
        payload: dict[str, Any] = {"tool": tool, "contract_version": contract_version, "arguments": dict(arguments)}
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        request = build_envelope(MESSAGE_REQUEST_EXECUTE, payload, self.binding, request_id=target_request_id)
        response = self._handle(request)
        validate_envelope(response, self.binding)
        return response["payload"]

    def status(self, request_id: str) -> dict[str, Any]:
        """查询指定请求状态。"""
        # 通过 request.status 获取执行器当前可观测状态
        request = build_envelope(MESSAGE_REQUEST_STATUS, {"target_request_id": request_id}, self.binding, request_id=request_id)
        response = self._handle(request)
        validate_envelope(response, self.binding)
        return response["payload"]

    def cancel(self, request_id: str, reason: str = "调用方请求取消") -> dict[str, Any]:
        """请求取消指定在途任务。"""
        # 使用独立消息随机数，关联原请求编号
        request = build_envelope(MESSAGE_REQUEST_CANCEL, {"reason": reason}, self.binding, request_id=request_id)
        response = self._handle(request)
        validate_envelope(response, self.binding)
        return response["payload"]

    def close(self) -> None:
        """关闭控制层会话并释放本地执行资源。"""
        # 先停止消息服务或子进程，再注销会话绑定
        if self._process is not None:
            if self._process.stdin is not None:
                self._process.stdin.close()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=2)
        elif self.server is not None:
            self.server.close()
        self.registry.close(self.binding.session_id)


def discover_executor() -> dict[str, Any]:
    """启动旧版能力发现入口并返回兼容报告。"""
    # 启动执行器子进程并注入项目根目录
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(root))
    result = subprocess.run([sys.executable, str(root / "windows_executor" / "main.py")], capture_output=True, text=True, check=True, env=env)
    report = json.loads(result.stdout)
    # 保留第一阶段 smoke 测试的旧语义；正式能力通过 ControlLayerService.capability 获取
    report["tools"] = []
    return report


def main() -> None:
    """执行最小注册与能力发现流程。"""
    # 校验开发期本机通道配置，缺少共享密钥时拒绝启动
    load_shared_secret()
    print(json.dumps(discover_executor(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
