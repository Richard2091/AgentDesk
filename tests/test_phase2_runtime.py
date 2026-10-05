"""第二阶段单会话运行闭环测试。"""

import time

import pytest

from control_layer.main import ControlLayerService
from shared.protocol import ProtocolError, SessionBinding, build_envelope, validate_envelope
from shared.schema import validate_schema
from windows_executor.main import ExecutorRuntime
from windows_executor.transport_main import ExecutorMessageServer


def test_capability_contains_default_system_info_and_matches_schema():
    """验证默认能力包含系统信息并符合冻结能力报告 Schema。"""
    service = ControlLayerService(secret=b"phase2-secret")
    try:
        report = service.capability()
        validate_schema(report, "capability-report.schema.json")
        assert [item["name"] for item in report["tools"]][0] == "windows.system.info"
        assert report["capability_epoch"] == service.capability()["capability_epoch"]
    finally:
        service.close()


def test_execute_success_invalid_arguments_and_idempotency():
    """验证成功、参数拒绝和同请求幂等返回。"""
    service = ControlLayerService(secret=b"phase2-secret")
    try:
        success = service.execute("windows.system.info", {}, timeout_ms=10000, request_id="same-request")
        assert success["status"] == "completed"
        assert set(success["result"]) == {"os_version", "executor_version"}
        repeated = service.execute("windows.system.info", {}, timeout_ms=10000, request_id="same-request")
        assert repeated["status"] == "completed"
        invalid = service.execute("windows.system.info", {"extra": True})
        assert invalid["status"] == "failed"
        assert invalid["error"]["code"] == "invalid_arguments"
    finally:
        service.close()


def test_permission_denied_and_unknown_fields_are_rejected():
    """验证会话身份权限拒绝和信封未知字段拒绝。"""
    binding = SessionBinding("session-test", "executor-test", "untrusted", "hmac-sha256", "test", b"phase2-secret")
    server = ExecutorMessageServer(binding)
    try:
        request = build_envelope("request.execute", {"tool": "windows.system.info", "contract_version": "0.1.0", "arguments": {}}, binding, request_id="permission-check")
        response = server.handle(request)
        assert response["payload"]["status"] == "failed"
        assert response["payload"]["error"]["code"] == "permission_denied"
        malformed = dict(request)
        malformed["unexpected"] = True
        error = server.handle(malformed)
        assert error["payload"]["error"]["code"] == "invalid_request"
    finally:
        server.close()


def test_declared_resource_and_action_policy_is_enforced():
    """验证工具声明的资源和动作必须命中调用主体权限白名单。"""
    runtime = ExecutorRuntime(enable_internal_test_tools=True)
    try:
        denied = runtime.execute("policy-check", "test.sleep", "0.1.0", {"duration_ms": 1}, subject="untrusted")
        assert denied["status"] == "failed"
        assert denied["error"]["code"] == "permission_denied"
        allowed = runtime.execute("policy-allowed", "test.sleep", "0.1.0", {"duration_ms": 1}, subject="control-layer")
        assert allowed["status"] == "completed"
    finally:
        runtime.shutdown()


def test_replay_is_rejected_without_second_execution():
    """验证同一 message_id 和 nonce 的重放被拒绝。"""
    service = ControlLayerService(secret=b"phase2-secret")
    try:
        request = build_envelope("request.execute", {"tool": "windows.system.info", "contract_version": "0.1.0", "arguments": {}}, service.binding, request_id="replay-check")
        first = service.server.handle(request)
        second = service.server.handle(request)
        assert first["payload"]["status"] in {"executing", "completed"}
        assert second["message_type"] == "message.error"
        assert second["payload"]["error"]["code"] == "replay_detected"
    finally:
        service.close()


def test_timeout_cancel_and_internal_error_paths():
    """验证内部测试工具仅显式开启时的超时、取消和异常路径。"""
    runtime = ExecutorRuntime(enable_internal_test_tools=True)
    try:
        timeout = runtime.execute("timeout", "test.sleep", "0.1.0", {"duration_ms": 100}, timeout_ms=10)
        assert timeout["status"] == "timeout"
        runtime.submit("cancel", "test.sleep", "0.1.0", {"duration_ms": 1000})
        assert runtime.cancel("cancel")["outcome"] == "requested"
        time.sleep(0.1)
        assert runtime.status("cancel")["status"] == "cancelled"
        failed = runtime.execute("failure", "test.fail", "0.1.0", {})
        assert failed["status"] == "failed"
    finally:
        runtime.shutdown()


def test_envelope_time_and_unknown_field_validation():
    """验证信封绑定校验拒绝未知字段和过期时间。"""
    binding = SessionBinding("session-test", "executor-test", "control-layer", "hmac-sha256", "test", b"phase2-secret")
    message = build_envelope("capability.query", {}, binding)
    validate_envelope(message, binding)
    message["unknown"] = 1
    with pytest.raises(ProtocolError) as exc_info:
        validate_envelope(message, binding)
    assert exc_info.value.code == "invalid_request"
    empty_request_id = build_envelope("request.status", {"target_request_id": "x"}, binding, request_id="")
    with pytest.raises(ProtocolError) as request_id_error:
        validate_envelope(empty_request_id, binding)
    assert request_id_error.value.code == "invalid_request"
