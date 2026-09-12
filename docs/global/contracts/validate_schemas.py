import json
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path(__file__).parent
for path in sorted((root / "schema").glob("*.schema.json")):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    print(f"通过：{path.name}")
