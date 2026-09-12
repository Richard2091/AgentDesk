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
