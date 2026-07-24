import json
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass(frozen=True)
class _Session:
    op_id: int
    # Services this operator may see. Admins get every service id at connect
    # time; the set is refreshed on reconnect, which is why the client
    # reconnects after its access flags change.
    service_ids: frozenset[int]


class WebSocketManager:
    """Fans out JSON events to connected operator tabs, scoped by service."""

    def __init__(self):
        self._connections: dict[WebSocket, _Session] = {}

    async def connect(self, ws: WebSocket, op_id: int, service_ids) -> bool:
        """Accept connection. Returns True if this is the operator's first tab."""
        await ws.accept()
        was_online = any(s.op_id == op_id for s in self._connections.values())
        self._connections[ws] = _Session(op_id, frozenset(service_ids))
        return not was_online

    def disconnect(self, ws: WebSocket) -> tuple[int | None, bool]:
        """Remove connection. Returns (op_id, went_offline) where went_offline is
        True when this was the operator's last tab."""
        session = self._connections.pop(ws, None)
        if session is None:
            return None, False
        still_connected = any(s.op_id == session.op_id for s in self._connections.values())
        return session.op_id, not still_connected

    async def broadcast(self, data: dict, service_id: int | None = None):
        """Send to every tab, or only to tabs allowed to see `service_id`.

        Without the filter an agent working brand A would receive brand B's
        messages in real time — pass service_id for anything dialog-related.
        """
        if not self._connections:
            return
        text = json.dumps(data, ensure_ascii=False)
        dead: set[WebSocket] = set()
        for ws, session in self._connections.items():
            if service_id is not None and service_id not in session.service_ids:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.pop(ws, None)
