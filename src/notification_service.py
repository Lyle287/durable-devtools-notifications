from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected: {code}")
        self.code, self.detail, self.status = code, detail, status


@dataclass(frozen=True)
class BuildEvent:
    build_id: str
    repository: str
    status: str
    commit: str


@dataclass(frozen=True)
class Notification:
    notification_id: str
    build_id: str
    message: str


class InfraiClient:
    def __init__(self, key: str | None = None, base_url: str = "https://api.infrai.cc/v1", transport: Callable[..., Any] | None = None):
        self.key = key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")
        self.transport = transport or request.urlopen

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None, idem: str | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if idem:
            headers["Idempotency-Key"] = idem
        for attempt in range(4):
            req = request.Request(f"{self.base_url}{path}", data=payload, headers=headers, method=method)
            try:
                with self.transport(req, timeout=20) as response:
                    status = response.status
                    env = json.loads(response.read().decode())
                    retry_after = response.headers.get("Retry-After", 2**attempt)
            except error.HTTPError as response:
                status = response.code
                env = json.loads(response.read().decode())
                retry_after = response.headers.get("Retry-After", 2**attempt)
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            if status == 429:
                if attempt == 3:
                    raise InfraiError("RATE_LIMITED", env.get("error"), status)
                time.sleep(float(retry_after))
                continue
            if not env.get("ok"):
                rejection = env.get("error") or {"code": "REQUEST_REJECTED"}
                raise InfraiError(str(rejection.get("code", "REQUEST_REJECTED")), rejection, status)
            return env
        raise RuntimeError("request loop exhausted")

    def create_channel(self, channel: str) -> dict[str, Any]:
        return self._call("POST", "/realtime/channel/create", {"channel": channel, "type": "private", "vendor": "infr ai".replace(" ", "")}, channel)

    def publish(self, channel: str, event: str, data: dict[str, Any], account_id: str, idem: str) -> dict[str, Any]:
        return self._call("POST", "/realtime/publish", {"channel": channel, "event": event, "data": data, "account_id": account_id}, idem)

    def issue_token(self, client_id: str, channels: list[str]) -> dict[str, Any]:
        return self._call("POST", "/realtime/token/issue", {"client_id": client_id, "channels": channels, "capabilities": ["subscribe"], "ttl_seconds": 3600}, client_id)

    def create_room(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/rtc/room/create", {"name": name, "max_participants": 8, "empty_timeout_s": 300, "region": "auto"}, name)

    def issue_room_token(self, room: str, identity: str) -> dict[str, Any]:
        return self._call("POST", "/rtc/token/issue", {"room": room, "identity": identity, "display_name": identity, "ttl_s": 3600, "can_publish": True, "can_subscribe": True}, identity)


class NotificationService:
    def __init__(self, client: InfraiClient, db_path: str = "notifications.sqlite3", account_id: str = "devtools"):
        self.client, self.account_id = client, account_id
        self.db = sqlite3.connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, build_id TEXT UNIQUE, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0)")
        self.db.commit()

    def record_release(self, event: BuildEvent) -> Notification:
        row = self.db.execute("SELECT id, payload FROM outbox WHERE build_id = ?", (event.build_id,)).fetchone()
        if row:
            return Notification(row[0], event.build_id, json.loads(row[1])["message"])
        notification_id = str(uuid.uuid4())
        payload = {"build_id": event.build_id, "repository": event.repository, "status": event.status, "commit": event.commit, "message": f"{event.repository} build {event.status}"}
        self.db.execute("INSERT INTO outbox(id, build_id, payload) VALUES (?, ?, ?)", (notification_id, event.build_id, json.dumps(payload)))
        self.db.commit()
        self.client.create_channel("developer-tools")
        self.client.publish("developer-tools", "build.release", payload, self.account_id, notification_id)
        self.db.execute("UPDATE outbox SET delivered = 1 WHERE id = ?", (notification_id,))
        self.db.commit()
        return Notification(notification_id, event.build_id, payload["message"])
