# AgentDesk

AgentDesk 规划让控制端智能体通过统一会话操作远程 Windows 电脑。当前仅有设计文档，尚无可运行的控制层、Executor 或 RustDesk 业务消息集成。

## 开始阅读

- [文档入口](docs/README.md)：全局规则及模块导航。
- [执行路线](docs/global/governance/roadmap.md)：先建立契约与只读闭环，再接入 MCP、RustDesk 和受控副作用能力。
- [开发进度](docs/global/progress/progress.md)：产品阶段仍未开始。
- [技术基线](docs/global/governance/technical-baseline.md)：选型与启动验收待办，尚无可执行启动命令。

## 产品愿景与范围

首期目标是单控制层、单 Windows Executor、单交互会话。智能体决定工具调用顺序，控制层执行会话、策略、确认、调度和审计；Executor 被动执行授权动作，设计职责见[架构总览](docs/global/architecture/architecture.md)。

计划先通过 Codex CLI 已有的 MCP 接入边界连接兼容客户端，并逐步提供系统查询、截图、窗口、文件、剪贴板、输入、进程、UI 自动化及受限 PowerShell。RustDesk 是规划中的远程画面、人工接管和业务消息承载方式，集成尚未验证。CLI、HTTP、WebSocket、SDK 多入口及多 Executor 属于后续扩展。

## 当前目录

当前 AgentDesk 目录包含本说明、协作约定及 `docs/` 文档树。工作区上级目录已核实存在两个独立源码目录：`D:\Program\AIProject\rustdesk` 保存 RustDesk 源码，`D:\Program\AIProject\codex-cli` 保存 Codex CLI 源码；它们不属于 AgentDesk 目录，版本和允许修改范围仍由技术基线管理。

## 安全与实施状态

远程桌面、系统权限和敏感内容按[安全设计](docs/global/security/security.md)控制；确认不代替授权，也不承诺能操作 Windows 安全桌面。协议、技术栈和安全机制仍处于草案阶段，未完成运行或真实环境验证。

