# AgentDesk 最小启动与验证

## 环境

- Python 3.11 或更高版本。
- 在项目根目录执行命令。

## 安装开发依赖

```powershell
python -m pip install -r requirements-dev.txt
```

## 运行自动化测试

```powershell
$env:PYTHONPATH = "."
python -m pytest -q
```

预期结果：第二阶段测试全部通过；当前基线为 26 项测试通过。

## 启动能力发现演示

```powershell
$env:AGENTDESK_SHARED_SECRET = "local-test-secret"
.\verify-start.ps1
```

脚本会启动控制层，控制层再启动 Executor，读取一份结构化能力报告并在成功时返回退出码 0。第二阶段正式能力发现和执行通过完整认证信封与 `windows_executor/transport_main.py` 传输入口验证；未认证的裸消息不会返回能力或执行结果。

也可以直接运行：

```powershell
$env:AGENTDESK_SHARED_SECRET = "local-test-secret"
python -m control_layer.main
```

## 协议 Schema 验证

```powershell
python docs/global/contracts/validate_schemas.py
```

## 第二阶段运行闭环

控制层服务在进程内提供 `capability`、`execute`、`submit`、`status` 和 `cancel` 操作；Executor 传输入口通过标准输入输出接收单行 UTF-8 JSON。正式消息必须包含协议版本、会话绑定、时间窗口、随机数和开发期 HMAC 签名。

可复现的真实子进程能力查询和异常载荷拒绝测试位于 `tests/test_phase2_transport.py`；控制层与 Executor 的请求、超时、取消、幂等和异常路径测试位于 `tests/test_phase2_runtime.py` 与 `tests/test_smoke.py`。

第二阶段只开放低风险的 `windows.system.info`，返回操作系统版本和 Executor 版本。测试工具必须显式启用，不进入默认能力报告。

## 跨机网络调用

Windows Executor 可通过 TCP 网关接受 Linux 端直接调用，不依赖 SSH。传输仍使用协议 0.1 单行 UTF-8 JSON 信封和 HMAC-SHA256 签名。

### Windows 端启动网关

```powershell
$env:PYTHONPATH = "."
$env:AGENTDESK_SHARED_SECRET = "your-shared-secret"
$env:AGENTDESK_NETWORK_HOST = "0.0.0.0"   # 默认 127.0.0.1（仅本机）；跨机改为 0.0.0.0 或 WireGuard 接口 IP
$env:AGENTDESK_NETWORK_PORT = "8765"
python -m windows_executor.network_main
```

### Linux 端调用

将仓库拷贝到 Linux 端（或通过 git clone），然后：

```bash
export AGENTDESK_SHARED_SECRET="your-shared-secret"
python linux_client/agentdesk_call.py capability --host <Windows-IP> --port 8765
python linux_client/agentdesk_call.py call --host <Windows-IP> --port 8765 --tool windows.system.info
```

输出为紧凑 JSON（`--raw` 输出完整响应信封）。退出码：成功 0，协议错误 1，连接异常 2。

### Claude Code / Codex 接入

在 Claude Code 或 Codex CLI 的 shell/bash 工具中直接执行上述命令即可。建议将调用封装为 shell 别名或脚本以简化 Agent 的调用方式。

### 安全边界

当前跨机传输使用开发期 HMAC-SHA256 共享密钥，不提供 TLS 加密。跨机部署建议在 WireGuard 隧道内使用，由 WireGuard 提供传输层加密。生产 Ed25519 认证属于后续阶段。

## 配置说明

共享密钥仅用于当前开发期本机闭环测试，不能视为生产认证；生产密钥管理和最终 Ed25519 会话认证属于后续阶段。详见 [CONFIGURATION.md](CONFIGURATION.md)。
