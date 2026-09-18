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

预期结果：第二阶段测试全部通过；当前基线为 23 项测试通过。

## 启动能力发现演示

```powershell
$env:AGENTDESK_SHARED_SECRET = "local-test-secret"
.\verify-start.ps1
```

脚本会启动控制层，控制层再启动 Executor，读取一份结构化能力报告并在成功时返回退出码 0。旧启动脚本保留第一阶段兼容输出；第二阶段正式能力发现和执行通过完整认证信封与 `windows_executor/transport_main.py` 传输入口验证。

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

## 配置说明

共享密钥仅用于当前开发期本机闭环测试，不能视为生产认证；生产密钥管理和最终 Ed25519 会话认证属于后续阶段。详见 [CONFIGURATION.md](CONFIGURATION.md)。
