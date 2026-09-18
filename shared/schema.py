"""冻结 JSON Schema 的运行时校验入口。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker, RefResolver


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "docs" / "global" / "contracts" / "schema"


class SchemaValidationError(ValueError):
    """Schema 校验失败，包含可展示的字段路径。"""

    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.path = path


def _load_schema(name: str) -> dict[str, Any]:
    """读取仓库内冻结 Schema 文件。"""
    # 读取固定目录，避免调用方传入任意文件路径
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def validate_schema(instance: Mapping[str, Any], schema_name: str) -> None:
    """按 Draft 2020-12 校验对象并在失败时抛出统一异常。"""
    # 构建带本地引用解析器，保证工具声明引用可用
    schema = _load_schema(schema_name)
    # 将仓库内引用 Schema 映射到冻结的本地 URI，禁止校验时访问网络
    store = {}
    for candidate in SCHEMA_DIR.glob("*.schema.json"):
        document = _load_schema(candidate.name)
        store[document.get("$id", candidate.as_uri())] = document
        store[candidate.name] = document
        store[f"https://agentdesk.local/schema/{candidate.name}"] = document
    resolver = RefResolver((SCHEMA_DIR / schema_name).as_uri(), schema, store=store)
    validator = Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(instance)), None)
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path)
        raise SchemaValidationError(error.message, path)


def validate_envelope_schema(envelope: Mapping[str, Any]) -> None:
    """校验消息信封的结构和 RFC3339 字段。"""
    # 冻结 Schema 中 request_id 是协议文档规定的请求可选字段，运行时补入同等严格约束
    schema = _load_schema("envelope.schema.json")
    if "request_id" in envelope:
        schema = copy.deepcopy(schema)
        schema["properties"]["request_id"] = {"type": "string", "minLength": 1}
    validate_schema(envelope, "envelope.schema.json") if "request_id" not in envelope else _validate_loaded_schema(envelope, schema, "envelope.schema.json")


def _validate_loaded_schema(instance: Mapping[str, Any], schema: Mapping[str, Any], schema_name: str) -> None:
    """使用本地引用映射校验已加载的临时 Schema。"""
    # 为临时 Schema 复用同一离线引用存储
    store = {}
    for candidate in SCHEMA_DIR.glob("*.schema.json"):
        document = _load_schema(candidate.name)
        store[document.get("$id", candidate.as_uri())] = document
        store[candidate.name] = document
        store[f"https://agentdesk.local/schema/{candidate.name}"] = document
    resolver = RefResolver((SCHEMA_DIR / schema_name).as_uri(), dict(schema), store=store)
    validator = Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(instance)), None)
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path)
        raise SchemaValidationError(error.message, path)


def validate_tool_declaration(declaration: Mapping[str, Any]) -> None:
    """校验工具声明的冻结字段和附加属性。"""
    validate_schema(declaration, "tool-declaration.schema.json")


def validate_message_payload(payload: Mapping[str, Any], definition: str) -> None:
    """按冻结消息载荷定义校验请求或响应对象。"""
    # 从唯一事实源读取指定 $defs，并拒绝不存在的定义名称
    schema_document = _load_schema("message-payloads.schema.json")
    schema = schema_document.get("$defs", {}).get(definition)
    if schema is None:
        raise ValueError(f"未知消息载荷定义: {definition}")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(payload)), None)
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path)
        raise SchemaValidationError(error.message, path)


def validate_error(error: Mapping[str, Any]) -> None:
    """校验统一结构化错误对象。"""
    validate_schema(error, "error.schema.json")
