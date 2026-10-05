import time

from control_layer.main import ControlLayerService, discover_executor
from windows_executor.main import ExecutorRuntime

def test_discover_executor():
    report = discover_executor()
    assert report["protocol_version"] == "0.1"
    assert "capability.query" in report["supported_messages"]
    assert report["tools"] == []
from shared.auth import sign_message, verify_message

def test_authenticated_message():
    message = {"session_id": "s1", "nonce": "n1", "issued_at": 100}
    secret = b"local-secret"
    signature = sign_message(message, secret)
    assert verify_message(message, signature, secret, now=100)

def test_tampered_message_rejected():
    message = {"session_id": "s1", "nonce": "n1", "issued_at": 100}
    secret = b"local-secret"
    signature = sign_message(message, secret)
    message["nonce"] = "changed"
    assert not verify_message(message, signature, secret, now=100)

def test_expired_message_rejected():
    message = {"session_id": "s1", "nonce": "n1", "issued_at": 100}
    secret = b"local-secret"
    signature = sign_message(message, secret)
    assert not verify_message(message, signature, secret, now=200)
from shared.replay import ReplayGuard


def test_replay_nonce_rejected():
    guard = ReplayGuard(ttl_seconds=30)
    assert guard.accept("s1", "n1", now=100)
    assert not guard.accept("s1", "n1", now=101)


def test_replay_nonce_isolated_by_session():
    guard = ReplayGuard(ttl_seconds=30)
    assert guard.accept("s1", "n1", now=100)
    assert guard.accept("s2", "n1", now=100)


def test_expired_nonce_can_be_removed():
    guard = ReplayGuard(ttl_seconds=30)
    assert guard.accept("s1", "n1", now=100)
    assert guard.accept("s1", "n1", now=131)
from shared.auth import sign_message
from shared.verifier import MessageVerifier

def test_message_verifier_combines_auth_and_replay():
    message = {"session_id": "s1", "nonce": "n1", "issued_at": 100}
    secret = b"local-secret"
    verifier = MessageVerifier(secret)
    signature = sign_message(message, secret)
    assert verifier.verify(message, signature, now=100)
    assert not verifier.verify(message, signature, now=100)
import json
import os
import subprocess
import sys
from pathlib import Path
from shared.protocol import SessionBinding, build_envelope, validate_envelope
from shared.schema import validate_schema
from shared.transport import encode_message, decode_message

def discover_executor_over_transport():
    """通过标准输入输出完成一次能力查询。"""
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(root))
    binding = SessionBinding("session-smoke", "executor-local", "control-layer", "hmac-sha256", "local-dev", b"local-test-secret")
    message = build_envelope("capability.query", {}, binding)
    env["AGENTDESK_SHARED_SECRET"] = "local-test-secret"
    env["AGENTDESK_SESSION_ID"] = binding.session_id
    env["AGENTDESK_EXECUTOR_ID"] = binding.executor_id
    result = subprocess.run([sys.executable, str(root / "windows_executor" / "transport_main.py")], input=encode_message(message), capture_output=True, text=True, encoding="utf-8", check=True, env=env)
    response = decode_message(result.stdout)
    validate_envelope(response, binding)
    validate_schema(response["payload"], "capability-report.schema.json")
    return response["payload"]

def test_structured_transport_roundtrip():
    message = {"message_type": "capability.query", "payload": {}}
    assert decode_message(encode_message(message)) == message

def test_executor_capability_over_transport():
    report = discover_executor_over_transport()
    assert report["supported_protocol_versions"] == ["0.1"]
    assert "windows.system.info" in {tool["name"] for tool in report["tools"]}


def test_phase2_success_and_capability():
    service = ControlLayerService(secret=b"local-secret")
    try:
        capability = service.capability()
        assert capability["tools"][0]["name"] == "windows.system.info"
        result = service.execute("windows.system.info", {}, timeout_ms=10000)
        assert result["status"] == "completed"
        assert result["result"]["executor_version"] == "0.1.0"
    finally:
        service.close()


def test_phase2_invalid_permission_and_idempotency():
    runtime = ExecutorRuntime(enable_internal_test_tools=True)
    service = ControlLayerService(secret=b"local-secret", runtime=runtime)
    try:
        invalid = service.execute("windows.system.info", {"unexpected": True}, request_id="req-invalid")
        assert invalid["status"] == "failed"
        assert invalid["error"]["code"] == "invalid_arguments"
        unsupported = service.execute("missing.tool", {}, request_id="req-missing")
        assert unsupported["status"] == "failed"
        assert unsupported["error"]["code"] == "unsupported_tool"
        first = service.execute("windows.system.info", {}, timeout_ms=10000, request_id="req-idempotent")
        second = service.execute("windows.system.info", {}, timeout_ms=10000, request_id="req-idempotent")
        assert first == second
        conflict = service.execute("windows.system.info", {}, timeout_ms=4000, request_id="req-idempotent")
        assert conflict["status"] == "failed"
        assert conflict["error"]["code"] == "request_conflict"
        assert service.status("req-idempotent")["status"] == "completed"
    finally:
        service.close()


def test_phase2_timeout_cancel_and_internal_error():
    runtime = ExecutorRuntime(enable_internal_test_tools=True)
    service = ControlLayerService(secret=b"local-secret", runtime=runtime)
    try:
        timeout = service.execute("test.sleep", {"duration_ms": 1000}, timeout_ms=20, request_id="req-timeout")
        assert timeout["status"] == "timeout"
        assert timeout["error"]["code"] == "timeout"

        request_id = "req-cancel"
        request = service.submit("test.sleep", {"duration_ms": 1000}, timeout_ms=500, request_id=request_id)
        assert request["status"] == "executing"
        ack = service.cancel(request_id)
        assert ack["outcome"] == "requested"
        deadline = time.time() + 2
        while time.time() < deadline:
            status = service.status(request_id)
            if status["status"] in {"cancelled", "completed"}:
                break
            time.sleep(0.01)
        assert status["status"] == "cancelled"

        failure = service.execute("test.fail", {}, request_id="req-failure")
        assert failure["status"] == "failed"
        assert failure["error"]["code"] == "internal_error"
    finally:
        service.close()
from shared.config import load_shared_secret

def test_missing_shared_secret_rejected(monkeypatch):
    monkeypatch.delenv("AGENTDESK_SHARED_SECRET", raising=False)
    try:
        load_shared_secret()
    except RuntimeError as exc:
        assert "缺少" in str(exc)
    else:
        raise AssertionError("缺失共享密钥时应拒绝启动")

def test_shared_secret_loaded(monkeypatch):
    monkeypatch.setenv("AGENTDESK_SHARED_SECRET", "测试密钥")
    assert load_shared_secret() == "测试密钥".encode("utf-8")
