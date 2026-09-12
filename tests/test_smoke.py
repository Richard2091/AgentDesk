from control_layer.main import discover_executor

def test_discover_executor():
    report = discover_executor()
    assert report["protocol_version"] == "0.1-draft"
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
from shared.transport import encode_message, decode_message

def discover_executor_over_transport():
    """通过标准输入输出完成一次能力查询。"""
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(root))
    message = {"message_type": "capability.query"}
    result = subprocess.run([sys.executable, str(root / "windows_executor" / "transport_main.py")], input=encode_message(message), capture_output=True, text=True, check=True, env=env)
    return decode_message(result.stdout)

def test_structured_transport_roundtrip():
    message = {"message_type": "capability.query", "payload": {}}
    assert decode_message(encode_message(message)) == message

def test_executor_capability_over_transport():
    report = discover_executor_over_transport()
    assert report["protocol_version"] == "0.1-draft"
    assert report["tools"] == []
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
