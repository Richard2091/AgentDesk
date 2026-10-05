"""Windows Executor 工具注册与请求执行实现。"""

from __future__ import annotations

import copy
import os
import platform
import sys
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from shared.errors import error_for
from shared.protocol import PROTOCOL_VERSION, TERMINAL_STATUSES, format_timestamp, utc_now
from shared.schema import validate_tool_declaration
from windows_executor.enhanced_tools import register_enhanced_tools


SYSTEM_INFO_DECLARATION = {
    "name": "windows.system.info", "version": "0.1.0", "description": "读取 Windows 系统和执行器版本。",
    "input_schema": {"type": "object", "additionalProperties": False},
    "output_schema": {"type": "object", "additionalProperties": False, "required": ["os_version", "executor_version"], "properties": {"os_version": {"type": "string"}, "executor_version": {"type": "string"}}},
    "executor": "windows", "risk_level": "low", "permissions": {"resource": "system.version", "actions": ["read"]}, "side_effects": "none",
    "default_timeout_ms": 3000, "max_timeout_ms": 10000, "cancellation": {"supported": True, "cleanup": "无副作用，无需清理"},
    "audit": {"record": "调用身份、工具、参数摘要、结果状态", "sensitive_fields": []}, "errors": ["permission_denied", "timeout", "internal_error"],
    "validation_cases": ["正常读取", "权限拒绝", "超时"],
}

PERMISSION_POLICY = {
    "control-layer": {
        "system.version": {"read"},
        "filesystem": {"read", "write"},
        "process": {"read", "execute"},
        "internal.test": {"read"},
    },
}


def _test_tools_enabled() -> bool:
    """读取是否允许暴露仅供测试的内部工具。"""
    # 只有显式环境变量值才启用测试工具，避免生产能力面扩大
    return os.environ.get("AGENTDESK_ENABLE_INTERNAL_TEST_TOOLS", "").lower() in {"1", "true", "yes"}


@dataclass
class RequestRecord:
    """单次请求的状态、结果和取消事件。"""

    request_id: str
    tool: str
    contract_version: str
    arguments: dict[str, Any]
    timeout_ms: int = 0
    status: str = "requested"
    result: Any = None
    error: dict[str, Any] | None = None
    duration_ms: int = 0
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: Future[Any] | None = None
    timeout_timer: threading.Timer | None = None


class ToolRegistry:
    """管理工具声明、实现函数和每次调用的参数/权限校验。"""

    def __init__(self, *, enable_internal_test_tools: bool | None = None):
        self._tools: dict[str, tuple[dict[str, Any], Callable[[dict[str, Any], threading.Event], Any]]] = {}
        self._enable_internal = _test_tools_enabled() if enable_internal_test_tools is None else enable_internal_test_tools
        self.register(SYSTEM_INFO_DECLARATION, self._system_info)
        # Register enhanced tools (file, process, exec)
        register_enhanced_tools(self)
        if self._enable_internal:
            self.register(self._sleep_declaration(), self._test_sleep)
            self.register(self._fail_declaration(), self._test_fail)

    def register(self, declaration: Mapping[str, Any], handler: Callable[[dict[str, Any], threading.Event], Any]) -> None:
        """校验并注册一项工具声明及实现。"""
        # 校验冻结声明并拒绝重复工具名称
        validate_tool_declaration(declaration)
        name = str(declaration["name"])
        if name in self._tools:
            raise ValueError(f"工具已注册: {name}")
        if declaration["default_timeout_ms"] > declaration["max_timeout_ms"]:
            raise ValueError("工具默认超时不能大于最大超时")
        self._tools[name] = (copy.deepcopy(dict(declaration)), handler)

    def get(self, name: str, version: str | None = None) -> tuple[dict[str, Any], Callable[[dict[str, Any], threading.Event], Any]] | None:
        """按名称和契约版本查找当前工具。"""
        # 仅返回版本匹配的真实声明与实现
        item = self._tools.get(name)
        if item is None or (version is not None and item[0]["version"] != version):
            return None
        return item

    def declarations(self) -> list[dict[str, Any]]:
        """返回当前完整工具声明副本。"""
        # 返回深拷贝，防止调用方篡改能力缓存
        return [copy.deepcopy(item[0]) for item in self._tools.values() if item[0].get("executor") != "internal"]

    @staticmethod
    def _system_info(arguments: dict[str, Any], cancel_event: threading.Event) -> dict[str, str]:
        """读取系统与执行器版本信息。"""
        # 该工具无副作用，取消事件仅用于统一处理接口
        del arguments, cancel_event
        # 只读取解释器提供的平台标识，避免版本探测触发额外系统调用
        return {"os_version": sys.platform, "executor_version": "0.1.0"}

    @staticmethod
    def _sleep_declaration() -> dict[str, Any]:
        """构造仅供测试的可取消休眠工具声明。"""
        return _internal_declaration("test.sleep", "测试用可取消休眠", {"type": "object", "additionalProperties": False, "required": ["duration_ms"], "properties": {"duration_ms": {"type": "integer", "minimum": 1}}})

    @staticmethod
    def _fail_declaration() -> dict[str, Any]:
        """构造仅供测试的内部异常工具声明。"""
        return _internal_declaration("test.fail", "测试用内部异常", {"type": "object", "additionalProperties": False})

    @staticmethod
    def _test_sleep(arguments: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
        """执行可取消的测试休眠。"""
        remaining = int(arguments["duration_ms"])
        # 以短间隔检查取消，确保测试不会阻塞到完整时长
        while remaining > 0:
            if cancel_event.wait(min(remaining, 25) / 1000):
                raise CancelledError()
            remaining -= min(remaining, 25)
        return {"slept_ms": int(arguments["duration_ms"])}

    @staticmethod
    def _test_fail(arguments: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
        """触发内部异常以覆盖失败路径。"""
        del arguments, cancel_event
        raise RuntimeError("internal test failure")


def _internal_declaration(name: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    """构造测试工具完整声明。"""
    return {
        "name": name, "version": "0.1.0", "description": description, "input_schema": input_schema, "output_schema": {"type": "object"}, "executor": "internal",
        "risk_level": "low", "permissions": {"resource": "internal.test", "actions": ["read"]}, "side_effects": "none", "default_timeout_ms": 3000, "max_timeout_ms": 10000,
        "cancellation": {"supported": True, "cleanup": "测试任务自动清理"}, "audit": {"record": "测试请求摘要", "sensitive_fields": []}, "errors": ["timeout", "cancelled", "internal_error"], "validation_cases": ["正常", "异常", "取消"],
    }


class CancelledError(Exception):
    """工具主动响应取消事件。"""


class ExecutorRuntime:
    """执行器请求流水线：查找、参数校验、权限校验、调度、超时、取消和结果归一化。"""

    def __init__(self, *, executor_id: str | None = None, enable_internal_test_tools: bool | None = None, max_workers: int = 4):
        self.executor_id = executor_id or "executor-local"
        self.capability_epoch = uuid.uuid4().hex
        self.registry = ToolRegistry(enable_internal_test_tools=enable_internal_test_tools)
        self._requests: dict[str, RequestRecord] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agentdesk-executor")

    def capability_report(self, *, in_reply_to: str | None = None) -> dict[str, Any]:
        """构造符合能力报告 Schema 的执行器能力。"""
        # 返回最新能力声明，能力变更时生成新的不透明纪元
        # 仅公开正式工具，内部测试工具必须留在执行器进程内
        declarations = [declaration for declaration in self.registry.declarations() if not declaration["name"].startswith("test.")]
        report = {"supported_protocol_versions": [PROTOCOL_VERSION], "supported_messages": ["capability.query", "capability.report", "request.execute", "request.status", "request.cancel", "result.final"], "capability_epoch": self.capability_epoch, "executor_version": "0.1.0", "os_version": sys.platform, "tools": declarations}
        if in_reply_to:
            report["in_reply_to"] = in_reply_to
        return report

    def execute(self, request_id: str, tool: str, contract_version: str, arguments: Mapping[str, Any], *, timeout_ms: int | None = None, subject: str = "control-layer") -> dict[str, Any]:
        """同步提交工具请求并等待统一终态结果。"""
        # 创建请求记录并执行入口校验
        record = self.submit(request_id, tool, contract_version, arguments, timeout_ms=timeout_ms, subject=subject)
        if record.status in TERMINAL_STATUSES:
            return self._final(record)
        return self.wait(request_id, timeout_ms=timeout_ms)

    def submit(self, request_id: str, tool: str, contract_version: str, arguments: Mapping[str, Any], *, timeout_ms: int | None = None, subject: str = "control-layer") -> RequestRecord:
        """校验并异步调度工具请求，支持相同请求幂等返回。"""
        with self._lock:
            # 查找已存在请求，防止同一业务编号重复调度
            existing = self._requests.get(request_id)
            if existing is not None:
                if existing.tool != tool or existing.contract_version != contract_version or existing.arguments != dict(arguments) or (timeout_ms is not None and existing.timeout_ms != timeout_ms):
                    # 冲突响应不能覆盖原请求，否则会破坏幂等状态和终态查询
                    return self._terminal_record(request_id, tool, contract_version, dict(arguments), "failed", error_for("request_conflict"), store=False)
                return existing
            # 查找工具并校验权限、参数及有效超时
            item = self.registry.get(tool, contract_version)
            if item is None:
                return self._terminal_record(request_id, tool, contract_version, dict(arguments), "failed", error_for("unsupported_tool"))
            declaration, handler = item
            if not self._is_authorized(subject, declaration):
                return self._terminal_record(request_id, tool, contract_version, dict(arguments), "failed", error_for("permission_denied"))
            validation = Draft202012Validator(declaration["input_schema"], format_checker=FormatChecker()).iter_errors(dict(arguments))
            first_error = next(iter(validation), None)
            if first_error is not None:
                details = {"path": ".".join(str(part) for part in first_error.absolute_path)}
                return self._terminal_record(request_id, tool, contract_version, dict(arguments), "failed", error_for("invalid_arguments", details=details))
            effective_timeout = declaration["default_timeout_ms"] if timeout_ms is None else timeout_ms
            if not isinstance(effective_timeout, int) or effective_timeout < 1 or effective_timeout > declaration["max_timeout_ms"]:
                return self._terminal_record(request_id, tool, contract_version, dict(arguments), "failed", error_for("invalid_arguments", details={"field": "timeout_ms"}))
            record = RequestRecord(request_id, tool, contract_version, dict(arguments), timeout_ms=effective_timeout)
            self._requests[request_id] = record
            record.status = "executing"
            record.updated_at = time.monotonic()
            record.future = self._pool.submit(self._run, record, handler, declaration, effective_timeout)
            return record

    def wait(self, request_id: str, *, timeout_ms: int | None = None) -> dict[str, Any]:
        """等待请求终态并在超时后触发取消。"""
        with self._lock:
            # 读取请求记录并等待后台任务完成
            record = self._requests.get(request_id)
        if record is None:
            return self._final(self._terminal_record(request_id, "", "", {}, "failed", error_for("request_not_found")))
        wait_seconds = None if timeout_ms is None else max(timeout_ms, 1) / 1000
        try:
            if record.future is not None:
                record.future.result(timeout=wait_seconds)
        except TimeoutError:
            self.cancel(request_id)
            self._finish(record, "timeout", None, error_for("timeout"))
        except Exception:
            if record.status not in TERMINAL_STATUSES:
                self._finish(record, "internal_error", None, error_for("internal_error"))
        return self._final(record)

    def cancel(self, request_id: str) -> dict[str, Any]:
        """请求取消在途任务并返回取消确认或当前终态。"""
        with self._lock:
            # 串行更新取消标志，后台任务负责完成终态清理
            record = self._requests.get(request_id)
            if record is None:
                return {"outcome": "not_found", "error": error_for("request_not_found")}
            if record.status in TERMINAL_STATUSES:
                return {"outcome": "already_terminal", "result": self._final(record)}
            record.status = "cancelling"
            record.updated_at = time.monotonic()
            record.cancel_event.set()
            return {"outcome": "requested"}

    def status(self, request_id: str) -> dict[str, Any]:
        """查询当前请求状态或统一终态结果。"""
        with self._lock:
            # 返回当前记录可观测字段，不暴露内部 Future
            record = self._requests.get(request_id)
        if record is None:
            return {"request_id": request_id, "status": "failed", "result": None, "error": error_for("request_not_found"), "duration_ms": 0}
        return self._final(record)

    def result_for(self, record: RequestRecord) -> dict[str, Any]:
        """将本次提交返回的记录转换为结果，支持未入库的冲突记录。"""
        # 冲突记录只用于当前响应，不能写入请求状态表
        return self._final(record)

    @staticmethod
    def _is_authorized(subject: str, declaration: Mapping[str, Any]) -> bool:
        """按调用主体、声明资源和动作执行最小权限判断。"""
        # 读取工具声明中的资源与动作，并与本阶段固定白名单求交
        permissions = declaration.get("permissions")
        if not isinstance(permissions, Mapping):
            return False
        resource = permissions.get("resource")
        actions = permissions.get("actions")
        if not isinstance(resource, str) or not resource or not isinstance(actions, list) or not actions:
            return False
        if not all(isinstance(action, str) and action for action in actions):
            return False
        allowed_actions = PERMISSION_POLICY.get(subject, {}).get(resource, set())
        return set(actions).issubset(allowed_actions)

    def shutdown(self, wait_timeout: float = 1.0) -> None:
        """请求在途任务停止，并在有限等待后释放线程池。"""
        # 先设置所有在途任务的合作式取消信号并停止计时器
        with self._lock:
            active = [record for record in self._requests.values() if record.status not in TERMINAL_STATUSES]
        for record in active:
            record.cancel_event.set()
            if record.timeout_timer is not None:
                record.timeout_timer.cancel()
        # 仅等待限定时间，避免不可合作工具无限阻塞关闭调用
        deadline = time.monotonic() + max(0.0, wait_timeout)
        for record in active:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or record.future is None:
                break
            try:
                record.future.result(timeout=remaining)
            except Exception:
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, record: RequestRecord, handler: Callable[[dict[str, Any], threading.Event], Any], declaration: Mapping[str, Any], timeout_ms: int) -> None:
        """在线程池中执行工具并校验输出模式。"""
        started = time.monotonic()
        timeout_timer = threading.Timer(timeout_ms / 1000, self._timeout_record, args=(record, started))
        timeout_timer.daemon = True
        timeout_timer.start()
        try:
            # 调用工具实现并检查取消标志
            result = handler(record.arguments, record.cancel_event)
            if record.cancel_event.is_set():
                self._finish(record, "cancelled", None, error_for("cancelled"), started)
                return
            # 校验工具输出，防止不符合契约的数据被报告为成功
            output_error = next(iter(Draft202012Validator(declaration["output_schema"]).iter_errors(result)), None)
            if output_error is not None:
                self._finish(record, "internal_error", None, error_for("internal_error", details={"phase": "output_validation"}), started)
                return
            self._finish(record, "completed", result, None, started)
        except CancelledError:
            self._finish(record, "cancelled", None, error_for("cancelled"), started)
        except Exception:
            # 协议将失败作为终态，具体原因通过 error.code=internal_error 表达
            self._finish(record, "failed", None, error_for("internal_error"), started)
        finally:
            # 任务完成后停止超时计时器，避免后台回调泄露
            timeout_timer.cancel()

    def _timeout_record(self, record: RequestRecord, started: float) -> None:
        """在后台任务超过工具截止时间时提交超时终态。"""
        # 设置取消信号并串行提交 timeout，工具仍需合作退出
        record.cancel_event.set()
        self._finish(record, "timeout", None, error_for("timeout"), started)

    def _finish(self, record: RequestRecord, status: str, result: Any, error: dict[str, Any] | None, started: float | None = None) -> None:
        """以串行方式提交一次请求终态。"""
        with self._lock:
            # 终态只允许提交一次，确保取消与完成竞争可观测
            if record.status in TERMINAL_STATUSES:
                return
            record.status = status
            record.result = result
            record.error = error
            record.duration_ms = int(max(0, (time.monotonic() - (started or record.created_at)) * 1000))
            record.updated_at = time.monotonic()
            if record.timeout_timer is not None:
                record.timeout_timer.cancel()

    def _terminal_record(self, request_id: str, tool: str, version: str, arguments: dict[str, Any], status: str, error: dict[str, Any], *, store: bool = True) -> RequestRecord:
        """创建已失败的请求记录并保留状态查询能力。"""
        record = RequestRecord(request_id, tool, version, arguments, status=status, error=error)
        if store:
            with self._lock:
                self._requests[request_id] = record
        return record

    @staticmethod
    def _final(record: RequestRecord) -> dict[str, Any]:
        """将内部请求记录转换为统一结果结构。"""
        return {"request_id": record.request_id, "status": record.status, "updated_at": format_timestamp(utc_now()), "result": record.result if record.status == "completed" else None, "error": record.error if record.status != "completed" else None, "duration_ms": record.duration_ms}


def build_capability_report(*, legacy: bool = False) -> dict[str, Any]:
    """构造能力报告；legacy 模式仅兼容第一阶段脚本输出。"""
    # 使用临时执行器读取真实注册工具
    runtime = ExecutorRuntime()
    report = runtime.capability_report()
    runtime.shutdown()
    if legacy:
        # 旧脚本字段保留在兼容输出，不参与新信封 Schema
        return {"protocol_version": PROTOCOL_VERSION, "executor_id": "executor-local", **report, "tools": []}
    return report


def main() -> None:
    """启动执行器并输出第一阶段兼容能力报告。"""
    # 保持旧启动脚本输出稳定，新运行时由 transport_main 驱动
    import json
    print(json.dumps(build_capability_report(legacy=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
