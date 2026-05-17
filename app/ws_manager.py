import json

from fastapi import WebSocket


class WebSocketManager:
    """Fans out JSON events to all connected operator browser tabs."""

    def __init__(self):
        self._connections: dict[WebSocket, int] = {}  # ws -> op_id

    async def connect(self, ws: WebSocket, op_id: int) -> bool:
        """Accept connection. Returns True if this is the operator's first tab."""
        await ws.accept()
        was_online = any(v == op_id for v in self._connections.values())
        self._connections[ws] = op_id
        return not was_online

    def disconnect(self, ws: WebSocket) -> tuple[int | None, bool]:
        """Remove connection. Returns (op_id, went_offline) where went_offline is
        True when this was the operator's last tab."""
        op_id = self._connections.pop(ws, None)
        if op_id is None:
            return None, False
        still_connected = any(v == op_id for v in self._connections.values())
        return op_id, not still_connected

    async def broadcast(self, data: dict):
        if not self._connections:
            return
        text = json.dumps(data, ensure_ascii=False)
        dead: set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.pop(ws, None)
