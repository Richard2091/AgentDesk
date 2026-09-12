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

当前仅验证最小注册与能力发现流程；认证、签名、防重放和真实 Windows 工具尚未实现。
