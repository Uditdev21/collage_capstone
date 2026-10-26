import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("event_bus")


class EventBus:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("WebSocket client connected. Total clients: %s", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info("WebSocket client disconnected. Total clients: %s", len(self.active_connections))

    async def broadcast(self, event_type: str, data: Any, device_id: Optional[str] = None):
        """Asynchronously send event JSON to all active WebSocket clients."""
        if not self.active_connections:
            return

        message = {
            "event": event_type,
            "device_id": device_id,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        dead_connections = set()
        for conn in list(self.active_connections):
            try:
                await conn.send_json(message)
            except Exception:
                dead_connections.add(conn)

        for dead in dead_connections:
            self.active_connections.discard(dead)

    def broadcast_threadsafe(self, event_type: str, data: Any, device_id: Optional[str] = None):
        """Threadsafe broadcast called from MQTT background threads."""
        if not self.active_connections:
            return

        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast(event_type, data, device_id),
                loop,
            )


event_bus = EventBus()
