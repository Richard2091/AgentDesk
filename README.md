# AgentDesk

面向 AI Agent 的 Windows 远程控制项目，用于补齐“本地电脑和 SSH Linux 之外，无法远程操作 Windows 桌面”的能力缺口。

> **项目状态：早期规划阶段**
> 当前仅包含设计文档，尚无可安装或可运行版本。

## 现有问题

现在的 AI Agent 通常只能操作运行自己的本地电脑，或者通过 SSH 控制 Linux 服务器。Windows 电脑上的桌面应用、窗口、文件和系统操作，仍缺少统一、安全、可审计的远程控制方式。

## 项目能做什么

AgentDesk 计划让 AI Agent 在授权范围内：

- 连接并管理远程 Windows 会话
- 查看系统、窗口、进程和文件信息
- 获取屏幕截图，理解当前桌面状态
- 操作剪贴板、键盘、鼠标和窗口
- 执行受限的 PowerShell 或其他系统操作
- 对调用执行身份认证、权限控制、人工确认和审计

以上是规划能力，尚未实现。

## 适用场景

- AI Agent 需要操作远程 Windows 桌面应用
- 自动查询 Windows 主机状态并返回结果
- 在人工确认后完成文件、窗口或输入操作
- 为远程桌面操作保留可追踪的调用记录

## 当前状态

项目处于第零阶段“技术基线”，完成度为 0%。当前没有安装命令、启动命令或可供体验的演示环境。

## 开始阅读

- [文档入口](docs/README.md)
- [执行路线](docs/global/governance/roadmap.md)
- [开发进度](docs/global/progress/progress.md)
- [技术基线](docs/global/governance/technical-baseline.md)
- [架构总览](docs/global/architecture/architecture.md)
- [安全设计](docs/global/security/security.md)

## 后续计划

首期将实现单控制层、单 Windows Executor 和单交互会话，先完成协议、认证、防重放、工具调度、低风险只读工具和审计闭环。MCP、RustDesk 及更多连接方式将在基础闭环完成后接入。

## 安全边界

协议、技术栈和安全机制仍在设计中，尚未完成运行或真实环境验证。高风险操作需要明确授权和人工确认；项目不承诺能够操作 Windows 安全桌面。

## 参与贡献

欢迎通过 [Issues](https://github.com/Richard2091/AgentDesk/issues) 提交问题和建议。贡献指南将在项目具备可运行代码后补充。

## 许可证

本项目采用 [MIT License](LICENSE)。
