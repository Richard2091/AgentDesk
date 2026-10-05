"""增强工具集合：文件、命令执行、进程、环境变量等 Agent 核心能力。

通过 register_enhanced_tools(registry) 注册到 ToolRegistry。
每个工具都遵循冻结协议 0.1 的声明规范，并通过 input/output Schema 校验。
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

# 安全边界：限制可访问的根目录，防止 Agent 读写系统关键路径
_ALLOWED_ROOTS = [
    Path(r"D:\data\AI\Projects"),
    Path(r"C:\Users\Richard\Documents"),
    Path(os.environ.get("AGENTDESK_WORKSPACE_ROOT", r"D:\data\AI\Projects\agentdesk")),
]

# 命令执行超时上限（毫秒）
_MAX_EXEC_TIMEOUT_MS = 120_000

# 输出大小上限（字节）
_MAX_OUTPUT_BYTES = 1_048_576  # 1 MB


def _is_path_allowed(path_str: str) -> bool:
    """检查路径是否在允许的根目录范围内。"""
    try:
        resolved = Path(path_str).resolve()
        return any(resolved.is_relative_to(root.resolve()) for root in _ALLOWED_ROOTS if root.exists())
    except (ValueError, OSError):
        return False


def _file_read_declaration() -> dict[str, Any]:
    return {
        "name": "windows.file.read",
        "version": "0.1.0",
        "description": "读取指定路径文件内容（UTF-8 编码）。",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string", "description": "绝对或相对路径"},
                "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
                "max_bytes": {"type": "integer", "description": "最大读取字节数，默认 65536"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["content", "path", "size_bytes", "truncated"],
            "properties": {
                "content": {"type": "string"},
                "path": {"type": "string"},
                "size_bytes": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
        },
        "executor": "windows",
        "risk_level": "medium",
        "permissions": {"resource": "filesystem", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 5000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "调用路径、文件大小", "sensitive_fields": ["content"]},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常读取", "路径不在允许范围", "文件不存在"],
    }


def _file_write_declaration() -> dict[str, Any]:
    return {
        "name": "windows.file.write",
        "version": "0.1.0",
        "description": "写入内容到指定路径文件（UTF-8 编码），支持覆盖和追加。",
        "input_schema": {
            "type": "object",
            "required": ["path", "content"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "append": {"type": "boolean", "description": "是否追加，默认 false（覆盖）"},
                "create_dirs": {"type": "boolean", "description": "是否自动创建父目录，默认 true"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "bytes_written", "created"],
            "properties": {
                "path": {"type": "string"},
                "bytes_written": {"type": "integer"},
                "created": {"type": "boolean"},
            },
        },
        "executor": "windows",
        "risk_level": "high",
        "permissions": {"resource": "filesystem", "actions": ["write"]},
        "side_effects": "local_write",
        "default_timeout_ms": 5000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "写入中断可能留下部分文件"},
        "audit": {"record": "目标路径、写入字节数、是否覆盖", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常写入", "路径不在允许范围", "只读目录"],
    }


def _file_list_declaration() -> dict[str, Any]:
    return {
        "name": "windows.file.list",
        "version": "0.1.0",
        "description": "列出目录内容，包括文件和子目录。",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "description": "是否递归列出，默认 false"},
                "max_entries": {"type": "integer", "description": "最大返回条目数，默认 200"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "entries", "total_count", "truncated"],
            "properties": {
                "path": {"type": "string"},
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "is_dir", "size_bytes"],
                        "properties": {
                            "name": {"type": "string"},
                            "is_dir": {"type": "boolean"},
                            "size_bytes": {"type": "integer"},
                        },
                    },
                },
                "total_count": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "filesystem", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 5000,
        "max_timeout_ms": 30000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "目录路径、条目数", "sensitive_fields": []},
        "errors": ["permission_denied", "invalid_request", "internal_error"],
        "validation_cases": ["正常列出", "目录不存在", "递归列出"],
    }


def _process_execute_declaration() -> dict[str, Any]:
    return {
        "name": "windows.process.execute",
        "version": "0.1.0",
        "description": "在 Windows 上执行命令并返回标准输出、标准错误和退出码。",
        "input_schema": {
            "type": "object",
            "required": ["command"],
            "additionalProperties": False,
            "properties": {
                "command": {"type": "string", "description": "要执行的命令行"},
                "cwd": {"type": "string", "description": "工作目录（可选）"},
                "timeout_ms": {"type": "integer", "description": "超时毫秒数"},
                "shell": {"type": "boolean", "description": "是否通过 shell 执行，默认 true"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["exit_code", "stdout", "stderr", "timed_out"],
            "properties": {
                "exit_code": {"type": ["integer", "null"]},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "timed_out": {"type": "boolean"},
            },
        },
        "executor": "windows",
        "risk_level": "high",
        "permissions": {"resource": "process", "actions": ["execute"]},
        "side_effects": "local_write",
        "default_timeout_ms": 30000,
        "max_timeout_ms": 120000,
        "cancellation": {"supported": True, "cleanup": "终止子进程"},
        "audit": {"record": "命令摘要、退出码、耗时", "sensitive_fields": ["command"]},
        "errors": ["permission_denied", "timeout", "internal_error"],
        "validation_cases": ["正常执行", "命令超时", "命令不存在"],
    }


def _process_list_declaration() -> dict[str, Any]:
    return {
        "name": "windows.process.list",
        "version": "0.1.0",
        "description": "列出当前运行的进程（PID、名称、内存）。",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_entries": {"type": "integer", "description": "最大返回条目数，默认 50"},
            },
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["processes"],
            "properties": {
                "processes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["pid", "name"],
                        "properties": {
                            "pid": {"type": "integer"},
                            "name": {"type": "string"},
                            "memory_mb": {"type": ["number", "null"]},
                        },
                    },
                }
            },
        },
        "executor": "windows",
        "risk_level": "low",
        "permissions": {"resource": "process", "actions": ["read"]},
        "side_effects": "none",
        "default_timeout_ms": 5000,
        "max_timeout_ms": 15000,
        "cancellation": {"supported": True, "cleanup": "无副作用"},
        "audit": {"record": "进程列表条目数", "sensitive_fields": []},
        "errors": ["permission_denied", "internal_error"],
        "validation_cases": ["正常列出"],
    }


def _handle_file_read(args: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    """读取文件内容并返回。"""
    raw_path = str(args["path"])
    if not _is_path_allowed(raw_path):
        raise PermissionError(f"路径不在允许范围内: {raw_path}")
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    encoding = str(args.get("encoding", "utf-8"))
    max_bytes = int(args.get("max_bytes", 65536))
    data = path.read_bytes()[:max_bytes]
    content = data.decode(encoding, errors="replace")
    return {
        "content": content,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "truncated": path.stat().st_size > max_bytes,
    }


def _handle_file_write(args: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    """写入文件内容。"""
    raw_path = str(args["path"])
    if not _is_path_allowed(raw_path):
        raise PermissionError(f"路径不在允许范围内: {raw_path}")
    path = Path(raw_path).resolve()
    content = str(args["content"])
    append = bool(args.get("append", False))
    create_dirs = bool(args.get("create_dirs", True))
    existed = path.exists()
    if create_dirs and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    data = content.encode("utf-8")
    with open(path, mode) as f:
        f.write(data)
    return {"path": str(path), "bytes_written": len(data), "created": not existed}


def _handle_file_list(args: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    """列出目录内容。"""
    raw_path = str(args["path"])
    if not _is_path_allowed(raw_path):
        raise PermissionError(f"路径不在允许范围内: {raw_path}")
    path = Path(raw_path).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"目录不存在: {path}")
    recursive = bool(args.get("recursive", False))
    max_entries = int(args.get("max_entries", 200))
    entries: list[dict[str, Any]] = []
    glob_pattern = "**/*" if recursive else "*"
    for item in sorted(path.glob(glob_pattern)):
        if len(entries) >= max_entries:
            break
        try:
            stat = item.stat()
            entries.append({
                "name": str(item.relative_to(path)),
                "is_dir": item.is_dir(),
                "size_bytes": stat.st_size if not item.is_dir() else 0,
            })
        except OSError:
            continue
    total = sum(1 for _ in path.glob(glob_pattern))
    return {"path": str(path), "entries": entries, "total_count": total, "truncated": total > max_entries}


def _handle_process_execute(args: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    """执行命令并返回输出。"""
    command = str(args["command"])
    cwd_raw = args.get("cwd")
    if cwd_raw is not None:
        if not _is_path_allowed(str(cwd_raw)):
            raise PermissionError(f"工作目录不在允许范围内: {cwd_raw}")
    timeout_ms = int(args.get("timeout_ms", 30000))
    timeout_ms = min(timeout_ms, _MAX_EXEC_TIMEOUT_MS)
    use_shell = bool(args.get("shell", True))
    try:
        proc = subprocess.Popen(
            command,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd_raw) if cwd_raw else None,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True
        stdout = (stdout or "")[:_MAX_OUTPUT_BYTES]
        stderr = (stderr or "")[:_MAX_OUTPUT_BYTES]
        exit_code = proc.returncode if not timed_out else None
        return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr, "timed_out": timed_out}
    except FileNotFoundError as exc:
        return {"exit_code": None, "stdout": "", "stderr": f"命令未找到: {exc}", "timed_out": False}


def _handle_process_list(args: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    """列出进程。"""
    import psutil
    max_entries = int(args.get("max_entries", 50))
    processes = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        if len(processes) >= max_entries:
            break
        try:
            mem = proc.info["memory_info"]
            processes.append({
                "pid": proc.info["pid"],
                "name": proc.info["name"] or "unknown",
                "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else None,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"processes": processes}


ENHANCED_DECLARATIONS: list[tuple[dict[str, Any], Callable]] = [
    (_file_read_declaration(), _handle_file_read),
    (_file_write_declaration(), _handle_file_write),
    (_file_list_declaration(), _handle_file_list),
    (_process_execute_declaration(), _handle_process_execute),
    (_process_list_declaration(), _handle_process_list),
]


def register_enhanced_tools(registry: Any) -> None:
    """将增强工具注册到 ToolRegistry。"""
    for declaration, handler in ENHANCED_DECLARATIONS:
        registry.register(declaration, handler)
