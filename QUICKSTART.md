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

预期结果：12 项测试通过。

## 启动能力发现演示

```powershell
$env:AGENTDESK_SHARED_SECRET = "local-test-secret"
.\verify-start.ps1
```

脚本会启动控制层，控制层再启动 Executor，读取一份结构化能力报告并在成功时返回退出码 0。当前报告只包含协议能力，不包含真实 Windows 工具。

也可以直接运行：

```powershell
$env:AGENTDESK_SHARED_SECRET = "local-test-secret"
python -m control_layer.main
```

## 协议 Schema 验证

```powershell
python docs/global/contracts/validate_schemas.py
```

## 配置说明

共享密钥仅用于当前开发期本机骨架测试，生产密钥管理和最终 Ed25519 会话认证属于后续阶段。详见 [CONFIGURATION.md](CONFIGURATION.md)。
