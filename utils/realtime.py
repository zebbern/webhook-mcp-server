"""Real-time delivery of captured requests over webhook.site's socket.io server.

webhook.site pushes a ``request.created`` event on the channel
``private-token.{token}`` (https://ws.webhook.site) as soon as a request,
email or DNSHook is captured. ``SocketWaiter`` wraps that so the wait tools
can react instantly while keeping HTTP polling as a backstop.

``python-socketio`` is imported lazily: without it, ``start()`` returns False
and callers fall back to polling.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

WS_URL = "https://ws.webhook.site"
CREATED_EVENT = "request.created"
_DROPPED: dict[str, Any] = {"__dropped__": True}

SocketFactory = Callable[[], Any]


def default_socket_factory() -> Any:
    """Build a python-socketio AsyncClient; raises ImportError when the extra is missing."""
    import socketio

    return socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)


class SocketWaiter:
    """Subscribe to one token's channel and hand out ``request.created`` payloads."""

    def __init__(self, token: str, api_key: str | None, factory: SocketFactory | None = None) -> None:
        self._token = token
        self._api_key = api_key
        self._factory = factory or default_socket_factory
        self._sio: Any = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribed = asyncio.Event()
        self._dropped = False

    @property
    def connected(self) -> bool:
        """False once the server closed the socket; callers then rely on polling."""
        return self._sio is not None and self._subscribed.is_set() and not self._dropped

    def _on_disconnect(self, *args: Any) -> None:
        self._dropped = True
        self._queue.put_nowait(_DROPPED)  # wake a pending next() so callers can switch to polling

    async def _on_connect(self) -> None:
        headers = {"Api-Key": self._api_key} if self._api_key else {}
        await self._sio.emit(
            "subscribe",
            {"channel": f"private-token.{self._token}", "auth": {"headers": headers}},
        )
        self._subscribed.set()

    def _on_created(self, *args: Any) -> None:
        data = args[-1] if args else None
        if isinstance(data, dict):
            self._queue.put_nowait(data)

    async def start(self, timeout: float) -> bool:
        """Connect and subscribe. False (never an exception) when realtime is unavailable."""
        try:
            self._sio = self._factory()
            self._sio.on("connect", self._on_connect)
            self._sio.on("disconnect", self._on_disconnect)
            self._sio.on(CREATED_EVENT, self._on_created)
            await asyncio.wait_for(self._sio.connect(WS_URL, transports=["websocket"]), timeout)
            await asyncio.wait_for(self._subscribed.wait(), timeout)
            return True
        except Exception:
            await self.close()
            return False

    async def next(self, timeout: float) -> dict[str, Any] | None:
        """Return the next event payload, or None when ``timeout`` passes or the socket drops."""
        if self._dropped:
            return None
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None
        return None if item is _DROPPED else item

    async def close(self) -> None:
        sio, self._sio = self._sio, None
        if sio is None:
            return
        try:
            await sio.disconnect()
        except Exception:
            pass
