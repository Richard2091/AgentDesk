# Windows Executor 文档

状态：第二阶段最小运行闭环已完成；真实 Windows 桌面工具仍未接入。

职责：在已登录的 Windows 交互会话中执行经认证和授权的请求，不运行模型或自主规划。

权威文档：[Executor 设计](../global/architecture/windows-executor.md)、[消息协议](../global/contracts/protocol.md)、[安全设计](../global/security/security.md)。

当前实现：`windows_executor/main.py` 提供工具注册表、能力报告、请求幂等、参数和权限校验、线程池调度、超时、合作式取消、结果 Schema 校验、结构化错误和有界关闭；`transport_main.py` 提供单次标准输入输出消息入口；`network_main.py` 提供 TCP 换行帧网络网关，支持多客户端连接，每连接独立会话绑定和重放防护。

已验证：`windows.system.info` 能从控制层闭环执行；参数错误、权限拒绝、声明资源/动作越权、未知工具、请求冲突、超时、取消、内部异常、重放、未知字段和未认证裸能力查询均有测试；真实 Executor 子进程的认证能力查询和载荷拒绝已通过集成测试。

安全边界：当前传输使用开发期 HMAC-SHA256 和进程内重放缓存，不是生产 Ed25519 认证。当前工具只读取系统版本和 Executor 版本，不读取用户名、主机名、屏幕、文件或进程信息。测试工具只有显式测试配置才注册。
