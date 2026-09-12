# AgentDesk 配置样例

## 本机共享密钥

启动前设置环境变量 `AGENTDESK_SHARED_SECRET`。该值仅用于本地开发测试，不得提交真实密钥：

```powershell
$env:AGENTDESK_SHARED_SECRET = "本地开发测试密钥"
python -m control_layer.main
```

缺少该配置时，程序必须拒绝启动。生产环境的密钥存储、轮换和吊销方案尚未冻结。
