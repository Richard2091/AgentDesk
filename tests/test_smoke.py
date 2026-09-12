from control_layer.main import discover_executor

def test_discover_executor():
    report = discover_executor()
    assert report["protocol_version"] == "0.1-draft"
    assert "capability.query" in report["supported_messages"]
    assert report["tools"] == []
