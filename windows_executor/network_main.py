"""Executor TCP 网络网关，将协议消息扩展到换行帧传输。"""

from __future__ import annotations

import asyncio
import os

from shared.transport import MAX_ENVELOPE_BYTES, decode_message, encode_message
from windows_executor.transport_main import ExecutorMessageServer, _binding_from_environment

DEFAULT_NETWORK_HOST = "127.0.0.1"
DEFAULT_NETWORK_PORT = 8765


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """处理单个客户端连接，使用独立会话绑定并串行处理消息。"""
    # 每个连接建立独立消息服务器，会话绑定与重放防护彼此隔离
    server = ExecutorMessageServer(_binding_from_environment())
    try:
        while True:
            try:
                line = await reader.readline()
            except ValueError:
                # 超过传输缓冲上限的帧按协议错误响应后关闭连接
                writer.write(
                    encode_message(server._error_response({}, "invalid_request", "消息超过传输上限")).encode("utf-8")
                )
                await writer.drain()
                break
            # 客户端关闭连接时 readline 返回空字节串
            if not line:
                break
            try:
                envelope = decode_message(line.decode("utf-8", errors="strict"))
            except Exception:
                # 解码失败时返回脱敏错误信封，保持连接可继续使用
                response = server._error_response({}, "invalid_request", "消息无法解析")
            else:
                # 同一连接逐条串行处理，避免并发访问执行器状态
                response = server.handle(envelope)
            writer.write(encode_message(response).encode("utf-8"))
            await writer.drain()
    except ConnectionError:
        # 连接中断或对端异常关闭时按正常断开处理
        pass
    finally:
        # 连接关闭时释放执行器线程池；置于清理最前保证取消场景也会执行
        server.close()
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def serve(host: str, port: int) -> None:
    """启动 TCP 网关并监听指定地址，直到进程被取消或中断。"""
    # 读取缓冲上限与协议单信封上限保持一致，避免超大消息占用内存
    tcp_server = await asyncio.start_server(
        _handle_client, host, port, limit=MAX_ENVELOPE_BYTES,
    )
    sockets = ", ".join(str(sock.getsockname()) for sock in tcp_server.sockets or [])
    print(f"AgentDesk 网络网关已监听 {sockets}", flush=True)
    # serve_forever 被取消时，async with 自动关闭监听套接字
    async with tcp_server:
        await tcp_server.serve_forever()


def main() -> None:
    """读取网络配置环境变量并启动 TCP 网关。"""
    # 跨机场景默认会话标识与 Linux 客户端保持一致
    os.environ.setdefault("AGENTDESK_SESSION_ID", "session-network")
    host = os.environ.get("AGENTDESK_NETWORK_HOST", DEFAULT_NETWORK_HOST)
    raw_port = os.environ.get("AGENTDESK_NETWORK_PORT", str(DEFAULT_NETWORK_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"无效的端口号: {raw_port}") from None
    if not 0 <= port <= 65535:
        raise SystemExit(f"端口号超出有效范围: {raw_port}")
    try:
        asyncio.run(serve(host, port))
    except KeyboardInterrupt:
        # Ctrl+C 触发取消后由 asyncio.run 完成任务回收，实现优雅退出
        pass


if __name__ == "__main__":
    main()
