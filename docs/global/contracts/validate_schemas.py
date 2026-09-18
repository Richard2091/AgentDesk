"""校验第一阶段冻结的 Schema 及固定正反例。"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parent
SCHEMA_DIR = ROOT / "schema"


def load_json(path: Path):
    """读取 UTF-8 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(schema, definition, value):
    """按消息载荷定义校验实例。"""
    validator_schema = {"$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"}
    Draft202012Validator(validator_schema).validate(value)


def main():
    """校验所有 Schema、工具声明及正反例。"""
    # 校验每个 Schema 自身结构。
    schemas = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        print(f"通过：{path.name}")

    # 校验信封正例和缺字段反例。
    envelope_validator = Draft202012Validator(schemas["envelope.schema.json"])
    envelope_validator.validate(load_json(SCHEMA_DIR / "examples" / "envelope.valid.json"))
    invalid_envelope = load_json(SCHEMA_DIR / "examples" / "envelope.invalid.missing-fields.json")
    if not list(envelope_validator.iter_errors(invalid_envelope)):
        raise AssertionError("信封反例未被拒绝")
    print("通过：信封正例和缺字段反例")

    # 校验每个消息载荷定义的代表性正例。
    payload_schema = schemas["message-payloads.schema.json"]
    payload_examples = {
        "requestExecute": {"tool": "windows.system.info", "contract_version": "0.1.0", "arguments": {}},
        "requestStatus": {"target_request_id": "req-1"},
        "requestCancel": {"reason": "用户取消"},
        "requestUpdate": {"request_id": "req-1", "status": "executing", "seq": 1},
        "statusResponse": {"request_id": "req-1", "status": "completed", "updated_at": "2026-09-18T00:00:00Z"},
        "progressEvent": {"seq": 1, "phase": "查询", "summary": "已完成", "percent": 100},
        "resultFinal": {"status": "completed", "result": {}, "error": None, "duration_ms": 1},
        "cancelAck": {"outcome": "requested"},
        "confirmationRequest": {"challenge_id": "ch-1", "tool": "x.y", "contract_version": "0.1.0", "arguments_digest": "sha256:1", "risk_level": "high", "summary": "需要确认", "challenge_expires_at": "2026-09-18T00:05:00Z"},
        "confirmationSubmit": {"challenge_id": "ch-1", "decision": "approve", "approver_subject": "user-1", "confirmation_token": "token-1"},
        "confirmationResult": {"challenge_id": "ch-1", "outcome": "approved"},
        "capabilityQuery": {},
        "messageError": {"in_reply_to": "m-1", "error": {}},
    }
    for definition, example in payload_examples.items():
        validate_payload(payload_schema, definition, example)

    # 批准决定必须携带一次性确认令牌。
    invalid_submit = {"challenge_id": "ch-1", "decision": "approve", "approver_subject": "user-1"}
    try:
        validate_payload(payload_schema, "confirmationSubmit", invalid_submit)
    except Exception:
        pass
    else:
        raise AssertionError("批准确认缺少令牌时未被拒绝")
    print(f"通过：{len(payload_examples)} 个消息载荷正例及确认条件反例")

    # 校验冻结的低风险工具声明。
    tool_schema = schemas["tool-declaration.schema.json"]
    Draft202012Validator(tool_schema).validate(load_json(ROOT / "windows.system.info.json"))
    print("通过：windows.system.info 工具声明")


if __name__ == "__main__":
    main()
