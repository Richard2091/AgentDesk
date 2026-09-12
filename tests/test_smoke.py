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
