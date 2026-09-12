# AgentDesk 消息协议草案

状态：设计草案，尚未冻结、未实现。本文件是消息字段、状态机和错误的唯一事实源；工具目录见[工具契约](tool-design.md)，认证、确认权限和防重放策略见[安全设计](../security/security.md)。

## 边界与版本

首期为单控制层、单 Executor、单交互会话。统一消息与传输解耦：最小闭环使用待选型的本地认证通道；RustDesk 接入阶段将相同消息承载到绑定的远程会话。连接建立和业务身份引导属于传输及认证设计，不能靠消息中自报身份完成认证。

拟定版本为 `0.1-draft`。冻结前允许整体修订，没有已发布客户端兼容承诺。双方必须显式支持同一版本；未知消息、未知字段、缺必填字段均拒绝，不静默降级。未来兼容升级规则在冻结前评审。

## 消息信封

所有业务消息使用以下字段。表中名称为机器字段，所有展示说明和错误文本使用中文。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `protocol_version` | 字符串 | 是 | 双方支持的消息版本 |
| `message_id` | 非空字符串 | 是 | 单条消息编号；业务重发需新建 |
| `message_type` | 字符串 | 是 | 下表定义的消息类型 |
| `session_id`、`executor_id` | 非空字符串 | 是 | 已认证连接绑定的会话及执行器 |
| `request_id` | 非空字符串 | 请求相关时 | 执行生命周期编号；能力查询、报告不携带 |
| `actor` | 对象 | 是 | 受认证的原始调用身份：`subject`、`auth_method`，由控制层可信传递 |
| `issued_at`、`expires_at` | 字符串 | 是 | 带 UTC 时区的消息有效期；确认挑战另有独立截止时间 |
| `nonce` | 非空字符串 | 是 | 单条消息随机数；不能作为执行幂等键 |
| `payload` | 对象 | 是 | 对应消息类型的载荷 |
| `signature` | 对象 | 是 | `algorithm`、`key_id`、`value`；签名者由可信密钥映射确定 |

签名覆盖除 `signature.value` 外的全部信封与载荷，包括算法和密钥标识。签名方法、编码、规范化算法、随机数要求、时钟容差、最大有效期及消息大小上限待评审；未确定时不得启用真实通道。响应由实际发送组件签名，`actor`仍表示该请求原始调用者；审批人单独记录，不能拿原调用者身份冒充审批人。

验证顺序：限制长度并解析 → 校验版本和字段 → 验证签名者及绑定身份 → 校验时间与重放 → 校验消息授权 → 处理请求状态。身份不可信的报文不触发任何动作，也不返回已有请求结果。

## 消息与载荷

| 类型 | 方向 | 必需载荷与含义 |
|---|---|---|
| `request.execute` | 控制层 → Executor | `tool`、`contract_version`、`arguments`；可选 `timeout_ms`，省略时用工具默认值 |
| `request.status` | 控制层 → Executor | 空对象，查询当前已认证身份拥有的请求状态或缓存终态 |
| `status.response` | Executor → 控制层 | `status`、`updated_at`，可选 `result`/`error`；仅返回查询方有权查看的状态 |
| `request.update` | Executor → 控制层 | `status`、`seq`，只报告 `awaiting_confirmation`、`executing` 或 `cancelling` 等非终态，序号单调递增 |
| `result.final` | Executor → 控制层 | `status`、`result`、`error`、`duration_ms`；只承载终态 |
| `progress.event` | Executor → 控制层 | `seq`、`phase`、`summary`；可选 `percent`，取值 0 至 100，表示运行进度而非成功 |
| `request.cancel` | 控制层 → Executor | `reason`，取消信封关联请求 |
| `cancel.ack` | Executor → 控制层 | `outcome`：`requested`、`already_terminal`、`not_cancellable`；后两者分别返回终态摘要或拒绝原因 |
| `confirmation.request` | Executor → 控制层 | `challenge_id`、`tool`、`contract_version`、`arguments_digest`、`risk_level`、`summary`、`challenge_expires_at`；该截止时间独立于信封有效期 |
| `confirmation.submit` | 控制层 → Executor | `challenge_id`、`decision`（`approve`或`reject`）、`approver_subject`；该字段只是声明，真实审批身份以签名密钥映射和受信控制层为准；批准时还需一次性 `confirmation_token` |
| `confirmation.result` | Executor → 控制层 | `challenge_id`、`outcome`（`approved`、`rejected`、`expired`、`invalid`）；无效时附 `error` |
| `capability.query` | 控制层 → Executor | 空对象，查询当前能力 |
| `capability.report` | Executor → 控制层 | `supported_protocol_versions`、`supported_messages`、`capability_epoch`、`executor_version`、`os_version`、`tools`；应答查询时附 `in_reply_to`消息编号 |
| `message.error` | 接收方 → 发送方 | `in_reply_to`、`error`；表示当前消息拒绝，不改变已存在请求的状态 |

对于无法安全建立关联的未认证消息，只记录脱敏的认证失败；如需响应，只能返回不含请求编号、状态或存在性信息的通用 `authentication_failed`。取消或查询不存在的请求返回 `request_not_found`。重复执行消息产生的错误不能把原请求变成失败。

### 能力发现

注册完成后执行器报告当前能力。操作系统版本和执行器版本是基础字段；屏幕、用户及权限摘要只有在当前身份获准读取时才可按后续冻结 Schema 扩展，不能默认泄露。工具列表为[工具契约](tool-design.md)声明数组，只包含真实可用能力。

`capability_epoch`为每次能力变更时更新的不透明版本。重连、进程重启、用户会话切换或权限变化后必须重新查询；控制层缓存不能授予权限。能力变更不自动修改已接受请求，执行前重新授权；工具撤销或契约不再匹配时拒绝执行。注册流程、更新通知和身份引导细节由模块设计验证后冻结。

### 结果与错误对象

`completed`时 `error=null`，`result`满足工具输出模式；其余终态 `result=null`、`error`必填。`duration_ms`为执行耗时，未执行为 0。取消、失败或超时不表示已撤销副作用，已发生的动作和清理结果记录为脱敏错误细节与审计。

错误统一使用 `code`、`message`、`retryable`、`details`；不再使用旧示例的 `type`。调用方只依赖 `code`和结构化字段。展示用 `message`为中文，`details`不得包含原始凭据或敏感内容。`retryable=true`只表示满足安全策略后可进行状态查询、重连或重新评估，不授权再次执行副作用。

| 错误码 | 含义 | 默认可重试 |
|---|---|---|
| `authentication_failed`、`permission_denied`、`policy_denied` | 认证、权限或策略拒绝 | 否 |
| `invalid_request`、`invalid_arguments` | 报文或参数错误 | 否 |
| `request_expired`、`replay_detected` | 消息过期或同一认证消息重放 | 否 |
| `request_conflict` | 同一请求编号的业务内容变化 | 否 |
| `request_not_found` | 当前身份范围内无该请求 | 否 |
| `confirmation_required`、`confirmation_invalid`、`confirmation_expired` | 尚需、无效或已过期确认 | 否 |
| `confirmation_rejected`、`cancelled` | 人工拒绝或已取消 | 否 |
| `unsupported_protocol`、`unsupported_message`、`unsupported_tool` | 版本、消息或工具不支持 | 否 |
| `executor_busy`、`executor_unavailable`、`transport_error` | 容量或连接故障 | 条件允许；先查询执行状态 |
| `timeout`、`internal_error`、`audit_unavailable` | 执行超时、内部异常或审计不可用 | 否 |

## 请求生命周期

控制层先完成入口身份、工具、参数及策略检查；需确认的请求进入执行器等待态，执行器创建并保管确认挑战。控制层展示挑战并核验审批人，再提交决定。审批令牌内容及权限规则仅见安全设计。

| 当前状态 | 允许后继 | 触发条件 |
|---|---|---|
| `requested` | `awaiting_confirmation`、`executing`、`rejected`、`cancelled`、`timeout` | 执行器接受、校验、排队或请求截止 |
| `awaiting_confirmation` | `executing`、`rejected`、`expired`、`cancelled` | 有效批准、拒绝/重新授权失败、挑战过期或取消 |
| `executing` | `completed`、`failed`、`timeout`、`cancelled` | 运行结果或停止完成 |

其余状态为终态，不可逆。`approved`只是确认决定，不是执行状态。批准后重新检查权限、会话与接管状态；校验失败进入 `rejected`，不执行。无效确认消息不销毁有效等待请求，返回消息错误；挑战自身到期才进入 `expired`。

`timeout_ms`从进入 `executing`开始计时；排队截止由首次执行消息的 `expires_at`限制，等待确认使用挑战有效期且不得超过该截止。确认提交本身也需未过期。三类截止不得因重试延长。挑战的最长有效期待安全评审确定。

`request.cancel`应答为 `requested`时仅表示已接收停止要求，不能视为取消成功；实际清理完成后才进入终态。无法安全中断的区段返回 `not_cancellable`并继续观察。取消与完成、确认与取消竞争时，执行器串行提交一次状态变化，失败的一方读取最新状态；不保证取消已发生的副作用。进度序号按请求单调递增，终态后的迟到进度丢弃。

## 幂等、重放与恢复

幂等范围为 `session_id + executor_id + actor.subject + request_id`。业务指纹包括工具、契约版本、参数、有效超时及首次截止，摘要算法和参数规范化待冻结。

同一认证消息的 `message_id/nonce`重复是重放，拒绝处理。合法重发必须使用新消息编号、随机数、时间和签名：同一幂等键且相同业务指纹只返回现有状态或终态，不再次执行；同键不同指纹返回 `request_conflict`。确认提交使用原请求编号及独立消息编号，不以重新发送执行请求来继续。

一次性令牌消费、请求状态迁移和调度占位必须以同一原子判定串行化。数据库事务或内存持久化方案待技术基线选型；未验证崩溃一致性前，重启或断连后结果未知的副作用请求禁止自动重放，必须人工核对。结果保留期、重放缓存和请求墓碑清理条件待冻结，不能通过清理记录允许旧请求重新执行。

## 冻结门禁

第一阶段需交付覆盖信封、全部载荷、工具声明和失败样例的 JSON Schema，并指定方言、格式验证及条件必填规则；本轮不创建接受任意载荷的空模式。完整 Schema 是冻结前的必需产物，目前未交付、未验证。

签名算法、密钥引导/轮换/吊销、摘要规范化、时钟/大小限制、权限和确认凭证模式、缓存保留与崩溃恢复规则未确认，均阻断协议冻结。负责人角色和验证要求见[技术基线](../governance/technical-baseline.md)，验收场景见[验证计划](../progress/validation-plan.md)。

