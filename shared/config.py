"""运行配置读取。"""
import os

def load_shared_secret():
    """读取本机消息共享密钥，缺失时拒绝启动。"""
    # 从环境变量读取共享密钥
    secret = os.environ.get("AGENTDESK_SHARED_SECRET")
    if not secret:
        raise RuntimeError("缺少 AGENTDESK_SHARED_SECRET 配置")
    # 返回 UTF-8 编码密钥
    return secret.encode("utf-8")
