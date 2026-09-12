# AgentDesk

## 现有问题

现在的 AI Agent 通常只能操作运行自己的本地电脑，或者通过远程 SSH 控制 Linux 服务器。对于 Windows 电脑，缺少一套安全、统一、可审计的远程控制方式，因此很多桌面应用、窗口、文件和系统操作仍然需要人工完成。

## 这个项目能做什么`r`n`r`nAgentDesk 计划提供面向 AI Agent 的 Windows 远程控制能力：`r`n`r`n- 让 AI Agent 连接并管理远程 Windows 会话`r`n- 查询 Windows 系统、窗口、进程和文件信息`r`n- 获取屏幕截图，辅助理解当前桌面状态`r`n- 操作剪贴板、键盘、鼠标和窗口`r`n- 在授权范围内执行 PowerShell 和其他受控操作`r`n- 对工具调用进行身份认证、权限控制、人工确认和审计记录`r`n- 通过统一接口适配不同的 AI 客户端和远程连接方式`r`n`r`n以上均为规划能力，当前尚未提供可运行版本。`r`n`r`n项目希望补上 AI Agent 从“只能操作本地电脑或 SSH Linux”到“能够安全控制远程 Windows 桌面”之间的能力缺口。`r`n`r`n## 开始阅读

- [文档入口](docs/README.md)：全局规则及模块导航。
- [执行路线](docs/global/governance/roadmap.md)：先建立契约与只读闭环，再接入 MCP、RustDesk 和受控副作用能力。
- [开发进度](docs/global/progress/progress.md)：产品阶段仍未开始。
- [技术基线](docs/global/governance/technical-baseline.md)：选型与启动验收待办，尚无可执行启动命令。

## 计划范围

首期目标是单控制层、单 Windows Executor、单交互会话。AI Agent 决定工具调用顺序，控制层负责会话、策略、确认、调度和审计；Executor 负责执行已授权动作。

计划先提供系统查询、截图、窗口、文件、剪贴板、输入、进程、UI 自动化及受限 PowerShell 等能力。RustDesk 计划用于远程画面、人工接管和业务消息承载，集成尚未验证。CLI、HTTP、WebSocket、SDK 多入口及多 Executor 属于后续扩展。

## 安全与实施状态

远程桌面、系统权限和敏感内容按[安全设计](docs/global/security/security.md)控制；确认不代替授权，也不承诺能操作 Windows 安全桌面。协议、技术栈和安全机制仍处于草案阶段，未完成运行或真实环境验证。

