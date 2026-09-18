"""第二阶段真实标准输入输出传输闭环测试。"""

import os
import subprocess
import sys
from pathlib import Path

from control_layer.main import ControlLayerService
from shared.protocol import SessionBinding, build_envelope, validate_envelope
from shared.schema import validate_message_payload, validate_schema
from shared.transport import decode_message, encode_message


def test_authenticated_capability_query_over_executor_process():
    """验证签名能力查询经真实 Executor 子进程往返并通过 Schema。"""
    root = Path(__file__).resolve().parent.parent
    binding = SessionBinding("session-transport", "executor-local", "control-layer", "hmac-sha256", "local-dev", b"transport-secret")
    request = build_envelope("capability.query", {}, binding)
    environment = dict(os.environ, PYTHONPATH=str(root), AGENTDESK_SHARED_SECRET="transport-secret", AGENTDESK_SESSION_ID=binding.session_id, AGENTDESK_EXECUTOR_ID=binding.executor_id)
    completed = subprocess.run(
        [sys.executable, str(root / "windows_executor" / "transport_main.py")],
        input=encode_message(request), capture_output=True, text=True, encoding="utf-8", check=True, env=environment,
    )
    response = decode_message(completed.stdout)
    validate_envelope(response, binding)
    assert response["message_type"] == "capability.report"
    validate_schema(response["payload"], "capability-report.schema.json")
    assert [tool["name"] for tool in response["payload"]["tools"]] == ["windows.system.info"]


def test_transport_rejects_unknown_execute_payload_field():
    """验证真实消息服务拒绝执行载荷中的未知字段。"""
    root = Path(__file__).resolve().parent.parent
    binding = SessionBinding("session-transport", "executor-local", "control-layer", "hmac-sha256", "local-dev", b"transport-secret")
    request = build_envelope("request.execute", {"tool": "windows.system.info", "contract_version": "0.1.0", "arguments": {}, "unexpected": True}, binding, request_id="transport-invalid")
    environment = dict(os.environ, PYTHONPATH=str(root), AGENTDESK_SHARED_SECRET="transport-secret", AGENTDESK_SESSION_ID=binding.session_id, AGENTDESK_EXECUTOR_ID=binding.executor_id)
    completed = subprocess.run(
        [sys.executable, str(root / "windows_executor" / "transport_main.py")],
        input=encode_message(request), capture_output=True, text=True, encoding="utf-8", check=True, env=environment,
    )
    response = decode_message(completed.stdout)
    validate_envelope(response, binding)
    assert response["message_type"] == "message.error"
    validate_message_payload(response["payload"], "messageError")
    assert response["payload"]["error"]["code"] == "invalid_request"


def test_transport_rejects_unauthenticated_capability_query():
    """验证裸能力查询不能绕过正式认证信封。"""
    root = Path(__file__).resolve().parent.parent
    environment = dict(os.environ, PYTHONPATH=str(root), AGENTDESK_SHARED_SECRET="transport-secret")
    completed = subprocess.run(
        [sys.executable, str(root / "windows_executor" / "transport_main.py")],
        input=encode_message({"message_type": "capability.query", "payload": {}}), capture_output=True, text=True, encoding="utf-8", check=True, env=environment,
    )
    response = decode_message(completed.stdout)
    assert response["message_type"] == "message.error"
    assert response["payload"]["error"]["code"] == "invalid_request"


def test_control_layer_executes_through_real_executor_subprocess():
    """验证控制层通过真实 Executor 子进程完成执行和状态查询。"""
    service = ControlLayerService(secret=b"subprocess-secret", use_subprocess=True)
    try:
        result = service.execute("windows.system.info", {}, timeout_ms=10000, request_id="subprocess-execute")
        assert result["status"] == "completed"
        assert result["result"]["executor_version"] == "0.1.0"
    finally:
        service.close()
