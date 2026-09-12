# 第一阶段 Schema 验收

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\docs\global\contracts\validate-schemas.ps1
```

通过条件：所有 Schema 可按 UTF-8 JSON 解析，且固定正例包含必填字段；固定反例缺少信封必填字段，必须被实现层拒绝。

当前证据：Schema 文件已完成 JSON 解析检查；本环境未安装 Python jsonschema（导入失败），因此字段约束的运行时拒绝仍未验证。待依赖纳入项目后执行正反例校验。

阻断项：签名算法、密钥生命周期、摘要规范化、确认令牌、缓存保留和崩溃恢复规则尚未完成决策，协议不能标记为冻结。

