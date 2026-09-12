"""消息随机数防重放缓存。"""
import time

class ReplayGuard:
    """按会话记录已消费随机数，阻止认证消息重复处理。"""
    def __init__(self, ttl_seconds=30):
        self.ttl_seconds = ttl_seconds
        self._seen = {}

    def accept(self, session_id, nonce, now=None):
        """校验并登记随机数，重复或过期返回 False。"""
        # 清理当前会话已过期的随机数
        current = int(time.time()) if now is None else now
        session = self._seen.setdefault(session_id, {})
        for old_nonce, timestamp in list(session.items()):
            if current - timestamp > self.ttl_seconds:
                del session[old_nonce]
        # 拒绝同一会话重复随机数
        if nonce in session:
            return False
        session[nonce] = current
        return True
