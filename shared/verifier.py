"""统一消息认证与防重放验证入口。"""
from shared.auth import verify_message
from shared.replay import ReplayGuard

class MessageVerifier:
    """组合消息签名、时间窗口和随机数防重放校验。"""
    def __init__(self, secret, replay_guard=None):
        self.secret = secret
        self.replay_guard = replay_guard or ReplayGuard()

    def verify(self, message, signature, now=None):
        """验证消息并登记随机数，返回校验结果。"""
        # 校验消息签名与有效时间
        if not verify_message(message, signature, self.secret, now=now):
            return False
        # 校验并登记随机数，阻止重复处理
        return self.replay_guard.accept(message["session_id"], message["nonce"], now=now)
