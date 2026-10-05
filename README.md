# AgentDesk

面向 AI Agent 的 Windows 远程控制项目，用于补齐“本地电脑和 SSH Linux 之外，无法远程操作 Windows 桌面”的能力缺口。

> **项目状态：第二阶段最小运行闭环已完成，当前仅为开发期本机闭环**

当前已具备单控制层、单 Executor、单会话和 `windows.system.info` 的结构化本机运行闭环，包含开发期 HMAC 信封认证、防重放、请求幂等、参数/结果 Schema 校验、超时、取消和结构化错误。真实 Windows 桌面工具及最终 Ed25519 运行时认证属于后续实现阶段。

## 项目能做什么

AgentDesk 计划让 AI Agent 在授权范围内连接 Windows 交互会话、查询系统和窗口、获取屏幕截图，并在人工确认后执行受控输入、文件、剪贴板、进程和脚本操作。

## 当前状态

- 第零阶段“技术基线”：已完成，完成度 100%。
- 第一阶段“协议冻结”：已完成，协议版本为 `0.1`，完成度 100%。
- 第二阶段“最小运行闭环”：已完成，完成度 100%。

跨机网络调用已作为最小实现交付：Windows Executor 可监听 TCP 端口，Linux 上的 Claude Code / Codex 通过 `linux_client/agentdesk_call.py` 直接调用，不依赖 SSH。部署方式见 [QUICKSTART.md](QUICKSTART.md)。

启动和测试方式见 [QUICKSTART.md](QUICKSTART.md)，阶段证据见 [开发进度](docs/global/progress/progress.md)。

## 开始阅读

- [文档入口](docs/README.md)
- [执行路线](docs/global/governance/roadmap.md)
- [开发进度](docs/global/progress/progress.md)
- [技术基线](docs/global/governance/technical-baseline.md)
- [架构总览](docs/global/architecture/architecture.md)
- [协议契约](docs/global/contracts/README.md)
- [安全设计](docs/global/security/security.md)

## 安全边界

当前交付不包含真实 Windows 桌面写操作，也不承诺操作安全桌面。高风险能力必须经过后续授权、人工确认、审计和接管门禁实现。

## 许可证

本项目采用 [MIT License](LICENSE)。
