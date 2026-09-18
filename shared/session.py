"""单执行器会话注册与绑定。"""

from __future__ import annotations

import secrets
import threading
import uuid

from shared.protocol import SessionBinding


class SessionRegistry:
    """维护开发期单执行器会话，并为信封提供不可变绑定。"""

    def __init__(self, secret: bytes, executor_id: str, *, subject: str = "control-layer", key_id: str = "local-dev"):
        self._secret = secret
        self._executor_id = executor_id
        self._subject = subject
        self._key_id = key_id
        self._lock = threading.RLock()
        self._active: SessionBinding | None = None

    def register(self) -> SessionBinding:
        """创建并登记一条新的单执行器认证会话。"""
        # 会话建立时生成不可预测标识并替换旧绑定
        with self._lock:
            self._active = SessionBinding(
                session_id="session-" + uuid.uuid4().hex,
                executor_id=self._executor_id,
                subject=self._subject,
                auth_method="hmac-sha256",
                key_id=self._key_id,
                secret=self._secret,
            )
            return self._active

    def current(self) -> SessionBinding | None:
        """返回当前会话绑定，不暴露可变内部状态。"""
        # 读取当前绑定供控制层构造请求
        with self._lock:
            return self._active

    def close(self, session_id: str | None = None) -> None:
        """关闭当前会话并使旧信封失效。"""
        # 仅关闭匹配的会话，避免旧连接误关闭新会话
        with self._lock:
            if self._active is not None and (session_id is None or self._active.session_id == session_id):
                self._active = None


def random_executor_id() -> str:
    """生成执行器注册标识。"""
    return "executor-" + secrets.token_hex(6)
