import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parent
schema_dir = root / "schema"
for path in sorted(schema_dir.glob("*.schema.json")):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    print(f"通过：{path.name}")

schema = json.loads((schema_dir / "envelope.schema.json").read_text(encoding="utf-8"))
examples = root / "schema" / "examples"
valid = json.loads((examples / "envelope.valid.json").read_text(encoding="utf-8"))
invalid = json.loads((examples / "envelope.invalid.missing-fields.json").read_text(encoding="utf-8"))
Draft202012Validator(schema).validate(valid)
print("通过：envelope.valid.json")
errors = list(Draft202012Validator(schema).iter_errors(invalid))
if not errors:
    raise AssertionError("反例未被拒绝")
print("通过：envelope.invalid.missing-fields.json 已拒绝")
