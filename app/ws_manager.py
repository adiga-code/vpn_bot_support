import json

from fastapi import WebSocket


class WebSocketManager:
    """Fans out JSON events to connected operator browser tabs.

    Каждое соединение помнит, к каким ВПН-сервисам допущен его оператор:
    событие по диалогу уходит только тем, у кого есть доступ к сервису этого
    диалога. Без этого оператор чужого сервиса видел бы чужие тикеты в
    реальном времени, даже если REST-эндпоинты их не отдают.
    """

    def __init__(self):
        self._connections: dict[WebSocket, int] = {}          # ws -> op_id
        self._services: dict[WebSocket, set[int]] = {}        # ws -> service ids

    async def connect(self, ws: WebSocket, op_id: int, service_ids: list[int]) -> bool:
        """Accept connection. Returns True if this is the operator's first tab."""
        await ws.accept()
        was_online = any(v == op_id for v in self._connections.values())
        self._connections[ws] = op_id
        self._services[ws] = set(service_ids or [])
        return not was_online

    def disconnect(self, ws: WebSocket) -> tuple[int | None, bool]:
        """Remove connection. Returns (op_id, went_offline) where went_offline is
        True when this was the operator's last tab."""
        self._services.pop(ws, None)
        op_id = self._connections.pop(ws, None)
        if op_id is None:
            return None, False
        still_connected = any(v == op_id for v in self._connections.values())
        return op_id, not still_connected

    def set_operator_services(self, op_id: int, service_ids: list[int]):
        """Флаги доступа поменяли на лету — обновить все вкладки оператора,
        не дожидаясь переподключения."""
        ids = set(service_ids or [])
        for ws, owner in self._connections.items():
            if owner == op_id:
                self._services[ws] = set(ids)

    async def broadcast(self, data: dict, service_id: int = None):
        """service_id=None — событие вне контекста сервиса (статусы операторов,
        системные): уходит всем."""
        if not self._connections:
            return
        text = json.dumps(data, ensure_ascii=False)
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            if service_id is not None and service_id not in self._services.get(ws, set()):
                continue
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.pop(ws, None)
            self._services.pop(ws, None)

    async def broadcast_counts(self, counts: dict[int, int]):
        """Счётчики на пилюлях сервисов. Каждой вкладке уходят только её
        сервисы — чужие цифры не должны утекать даже как числа в payload."""
        for sock in list(self._services):
            sids = self._services.get(sock, set())
            payload = {"type": "service_counts",
                       "counts": {str(sid): counts.get(sid, 0) for sid in sids}}
            try:
                await sock.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                self._connections.pop(sock, None)
                self._services.pop(sock, None)

    async def send_to_operator(self, op_id: int, data: dict):
        """Точечное событие одному оператору (смена его же флагов доступа)."""
        text = json.dumps(data, ensure_ascii=False)
        for ws, owner in list(self._connections.items()):
            if owner != op_id:
                continue
            try:
                await ws.send_text(text)
            except Exception:
                self._connections.pop(ws, None)
                self._services.pop(ws, None)
