# 第一阶段 Schema 验收

运行正式校验：

```powershell
python docs/global/contracts/validate_schemas.py
```

通过条件：所有 Draft 2020-12 Schema 结构有效；全部消息载荷正例、工具声明正例和固定反例均按约束验证。

当前证据：已安装 requirements-dev.txt 中的 jsonschema 依赖；全部 9 个 Schema、13 个消息载荷正例、确认令牌条件反例、信封缺字段反例和 windows.system.info 工具声明均验证通过。

后续范围：Ed25519 运行时签名、密钥轮换/吊销、确认令牌消费和崩溃恢复属于后续运行时阶段；本阶段已冻结其接口参数和安全边界。


依赖安装：python -m pip install -r requirements-dev.txt；正式校验：python docs/global/contracts/validate_schemas.py。
