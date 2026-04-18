"""
WebSocket terminal bridge.

Flow:
  Browser (xterm.js) ←─ WebSocket ─→ FastAPI endpoint ─→ Docker/K8s exec stream

The terminal handler attaches to the running container's PTY and
bidirectionally streams bytes between the browser and the container.

For Docker:  uses docker-py's attach_socket() with a raw TCP connection.
For K8s:     uses kubernetes-client's connect_get_namespaced_pod_exec with tty=True.
"""

from __future__ import annotations

import asyncio

import docker
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.stream import stream as k8s_stream

from app.core.config import settings

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL = 20  # seconds


async def docker_terminal_handler(websocket: WebSocket, container_id: str) -> None:
    """
    Attach to a Docker container PTY and forward I/O over WebSocket.
    Each WebSocket message is raw bytes sent to the container stdin.
    Container stdout/stderr is forwarded back to the client.
    """
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        await websocket.close(code=4404, reason="Container not found")
        return

    # Attach raw socket to container PTY
    socket = container.attach_socket(params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1})
    socket._sock.setblocking(False)

    loop = asyncio.get_event_loop()

    async def read_container() -> None:
        """Forward container output → WebSocket."""
        try:
            while True:
                data = await loop.run_in_executor(None, _read_nonblocking, socket._sock)
                if data is None:
                    await asyncio.sleep(0.01)
                    continue
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def write_container() -> None:
        """Forward WebSocket input → container stdin."""
        try:
            while True:
                data = await websocket.receive_bytes()
                await loop.run_in_executor(None, socket._sock.sendall, data)
        except WebSocketDisconnect:
            pass

    async def heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await websocket.send_text("ping")
        except (WebSocketDisconnect, RuntimeError):
            pass

    tasks = [
        asyncio.create_task(read_container()),
        asyncio.create_task(write_container()),
        asyncio.create_task(heartbeat()),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        socket.close()
        logger.info("terminal_session_ended", container=container_id)


def _read_nonblocking(sock) -> bytes | None:  # type: ignore[no-untyped-def]
    import errno
    import socket as _socket
    try:
        return sock.recv(4096)
    except BlockingIOError:
        return None
    except _socket.error as e:
        if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        raise


async def kubernetes_terminal_handler(websocket: WebSocket, pod_name: str) -> None:
    """
    Stream a PTY session from a Kubernetes pod over WebSocket.
    Uses binary framing: first byte is channel (0=stdin, 1=stdout, 2=stderr).
    """
    if settings.K8S_IN_CLUSTER:
        k8s_config.load_incluster_config()
    else:
        k8s_config.load_kube_config(config_file=settings.K8S_KUBECONFIG_PATH)

    core_v1 = k8s_client.CoreV1Api()

    ws_client = k8s_stream(
        core_v1.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=settings.K8S_NAMESPACE,
        command=["/bin/bash"],
        container="lab",
        stderr=True,
        stdin=True,
        stdout=True,
        tty=True,
        _preload_content=False,
    )

    loop = asyncio.get_event_loop()

    async def read_pod() -> None:
        try:
            while ws_client.is_open():
                ws_client.update(timeout=0.1)
                if ws_client.peek_stdout():
                    data = ws_client.read_stdout()
                    await websocket.send_text(data)
                if ws_client.peek_stderr():
                    data = ws_client.read_stderr()
                    await websocket.send_text(data)
                await asyncio.sleep(0.01)
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def write_pod() -> None:
        try:
            while True:
                data = await websocket.receive_text()
                ws_client.write_stdin(data)
        except WebSocketDisconnect:
            pass

    tasks = [
        asyncio.create_task(read_pod()),
        asyncio.create_task(write_pod()),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        ws_client.close()
        logger.info("k8s_terminal_session_ended", pod=pod_name)


async def get_terminal_handler(websocket: WebSocket, container_id: str) -> None:
    """Dispatch to Docker or K8s handler based on settings."""
    if settings.ORCHESTRATOR == "kubernetes":
        await kubernetes_terminal_handler(websocket, container_id)
    else:
        await docker_terminal_handler(websocket, container_id)
