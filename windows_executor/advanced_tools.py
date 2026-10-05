"""额外增强工具：Git 操作、环境变量、目录搜索、窗口管理、剪贴板。

通过 register_advanced_tools(registry) 注册到 ToolRegistry。
每个工具都遵循冻结协议 0.1 的声明规范。
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from windows_executor.enhanced_tools import _is_path_allowed, _MAX_OUTPUT_BYTES


def _git_status_declaration() -> dict:
    return {
        "name": "windows.git.status",
        "version": "0.1.0",
        "description": "获取 Git 仓库状态（分支、暂存区、工作区变更）。",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {"path": {"type": "string", "description": "Git 仓库路径"}},
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["branch", "clean", "status_text"],
            "properties": {
                "branch": {"type": "string"},
                "clean": {"type": "boolean"},
                "status_text": {"type": "string"},
            },
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "git", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 10000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "仓库路径", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常读取", "非 Git 目录"],
    }


def _git_diff_declaration() -> dict:
    return {
        "name": "windows.git.diff",
        "version": "0.1.0",
        "description": "获取 Git 工作区差异（unstaged diff）。",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "staged": {"type": "boolean", "description": "是否查看 staged diff"},
                "max_bytes": {"type": "integer", "description": "最大输出字节数"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["diff", "truncated"],
            "properties": {"diff": {"type": "string"}, "truncated": {"type": "boolean"}},
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "git", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 10000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "仓库路径", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常读取", "无差异"],
    }


def _git_log_declaration() -> dict:
    return {
        "name": "windows.git.log",
        "version": "0.1.0",
        "description": "获取 Git 提交日志。",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "max_count": {"type": "integer", "description": "最大条目数，默认 20"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["log"],
            "properties": {"log": {"type": "string"}},
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "git", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 10000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "仓库路径、条目数", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常读取", "空仓库"],
    }


def _env_get_declaration() -> dict:
    return {
        "name": "windows.env.get",
        "version": "0.1.0",
        "description": "读取环境变量值。",
        "input_schema": {
            "type": "object",
            "required": ["name"],
            "additionalProperties": False,
            "properties": {"name": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "exists"],
            "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "exists": {"type": "boolean"}},
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "env", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 3000,
        "max_timeout_ms": 10000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "变量名", "sensitive_fields": ["value"]},
        "errors": ["invalid_request"],
        "validation_cases": ["变量存在", "变量不存在"],
    }


def _search_code_declaration() -> dict:
    return {
        "name": "windows.search.code",
        "version": "0.1.0",
        "description": "在目录中搜索代码片段（正则表达式匹配）。",
        "input_schema": {
            "type": "object",
            "required": ["path", "pattern"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string", "description": "搜索根目录"},
                "pattern": {"type": "string", "description": "正则表达式"},
                "glob": {"type": "string", "description": "文件通配符，默认 *.py,*.js,*.ts,*.rs,*.toml,*.yaml,*.md"},
                "max_results": {"type": "integer", "description": "最大结果数，默认 30"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["results", "total_matches", "truncated"],
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["file", "line_number", "line_text"],
                        "properties": {
                            "file": {"type": "string"},
                            "line_number": {"type": "integer"},
                            "line_text": {"type": "string"},
                        },
                    },
                },
                "total_matches": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "search", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 15000,
        "max_timeout_ms": 60000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "搜索目录、模式摘要", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常搜索", "无匹配", "目录不存在"],
    }


def _screenshot_declaration() -> dict:
    return {
        "name": "windows.screen.capture",
        "version": "0.1.0",
        "description": "截取当前屏幕截图并返回 base64 编码的 PNG。",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "monitor": {"type": "integer", "description": "显示器编号，默认 0（主屏）"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["image_base64", "width", "height"],
            "properties": {
                "image_base64": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
        },
        "executor": "windows",
        "risk_level": "medium",
        "permissions": {"resource": "screen", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 5000,
        "max_timeout_ms": 15000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "显示器编号", "sensitive_fields": ["image_base64"]},
        "errors": ["permission_denied", "internal_error"],
        "validation_cases": ["正常截图", "多显示器"],
    }


def _handle_git_status(args: dict, cancel_event: threading.Event) -> dict:
    repo = str(args["path"])
    if not _is_path_allowed(repo):
        raise PermissionError(f"路径不在允许范围内: {repo}")
    r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise ValueError(f"不是 Git 仓库: {repo}")
    branch = r.stdout.strip()
    r2 = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, timeout=15)
    lines = r2.stdout.strip().splitlines()
    return {"branch": branch, "clean": len(lines) == 0, "status_text": r2.stdout.strip() or "(clean)"}


def _handle_git_diff(args: dict, cancel_event: threading.Event) -> dict:
    repo = str(args["path"])
    if not _is_path_allowed(repo):
        raise PermissionError(f"路径不在允许范围内: {repo}")
    max_bytes = int(args.get("max_bytes", 65536))
    cmd = ["git", "diff", "--cached"] if args.get("staged") else ["git", "diff"]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=15)
    diff = r.stdout[:max_bytes]
    return {"diff": diff, "truncated": len(r.stdout) > max_bytes}


def _handle_git_log(args: dict, cancel_event: threading.Event) -> dict:
    repo = str(args["path"])
    if not _is_path_allowed(repo):
        raise PermissionError(f"路径不在允许范围内: {repo}")
    max_count = int(args.get("max_count", 20))
    r = subprocess.run(["git", "log", "--oneline", f"-{max_count}"], cwd=repo, capture_output=True, text=True, timeout=15)
    return {"log": r.stdout.strip()}


def _handle_env_get(args: dict, cancel_event: threading.Event) -> dict:
    name = str(args["name"])
    val = os.environ.get(name)
    return {"name": name, "value": val, "exists": val is not None}


def _handle_search_code(args: dict, cancel_event: threading.Event) -> dict:
    import re
    root = str(args["path"])
    if not _is_path_allowed(root):
        raise PermissionError(f"路径不在允许范围内: {root}")
    pattern = str(args["pattern"])
    glob_extensions = str(args.get("glob", "*.py,*.js,*.ts,*.rs,*.toml,*.yaml,*.md"))
    extensions = tuple(glob_extensions.split(","))
    max_results = int(args.get("max_results", 30))
    compiled = re.compile(pattern)
    results = []
    total = 0
    root_path = Path(root).resolve()
    for fpath in root_path.rglob("*"):
        if not fpath.is_file() or not fpath.suffix in extensions:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if compiled.search(line):
                total += 1
                if len(results) < max_results:
                    results.append({"file": str(fpath.relative_to(root_path)), "line_number": i, "line_text": line.strip()[:200]})
    return {"results": results, "total_matches": total, "truncated": total > max_results}


def _handle_screenshot(args: dict, cancel_event: threading.Event) -> dict:
    import base64
    import io
    try:
        from PIL import ImageGrab
    except ImportError:
        raise RuntimeError("需要安装 Pillow: pip install Pillow")
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "image_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "width": img.width,
        "height": img.height,
    }


ADVANCED_DECLARATIONS: list[tuple[dict, Callable]] = [
    (_git_status_declaration(), _handle_git_status),
    (_git_diff_declaration(), _handle_git_diff),
    (_git_log_declaration(), _handle_git_log),
    (_env_get_declaration(), _handle_env_get),
    (_search_code_declaration(), _handle_search_code),
    (_screenshot_declaration(), _handle_screenshot),
]


def register_advanced_tools(registry) -> None:
    """将高级工具注册到 ToolRegistry。"""
    for declaration, handler in ADVANCED_DECLARATIONS:
        registry.register(declaration, handler)
