# AgentDesk 最小骨架

## 启动

在项目根目录执行：

```powershell
python -m control_layer.main
```

该命令启动 Executor 子进程，完成一次能力发现并输出结构化结果。

## 测试

```powershell
python -m pytest
```

当前已验证最小注册、能力发现、消息认证、防重放和结构化消息通道；真实 Windows 工具尚未实现。

## 配置

先设置 AGENTDESK_SHARED_SECRET，详见 [CONFIGURATION.md](CONFIGURATION.md)。

