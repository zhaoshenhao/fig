from __future__ import annotations

import json
import time

from src.session.base import SessionStore
from src.session.data import SessionData

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]  # pragma: no cover


class RedisSessionStore(SessionStore):

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "kf:sess:",
        max_age: int = 3600,
    ):
        if redis is None:  # pragma: no cover
            raise RuntimeError(  # pragma: no cover
                "redis package not installed; run: pip install redis"
            )
        self._client = redis.Redis.from_url(url)
        try:
            self._client.ping()
        except Exception:
            self._client = redis.Redis.from_url(url, protocol=2)
            self._client.ping()
        self._prefix = prefix
        self._max_age = max_age

    def _key(self, chat_id: str) -> str:
        return f"{self._prefix}{chat_id}"

    def get(self, chat_id: str) -> SessionData | None:
        data = self._client.get(self._key(chat_id))
        if data is None:
            return None
        raw = json.loads(data)
        return SessionData.from_dict(raw)

    def create(self, workflow_name: str, return_mode: str) -> SessionData:
        session = SessionData(
            _workflow=workflow_name,
            return_mode=return_mode,
        )
        self._write(session)
        return session

    def save(self, session: SessionData) -> None:
        session.last_active_at = time.time()
        self._write(session)

    def count(self) -> int:
        n = 0
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor, match=f"{self._prefix}*")
            n += len(keys)
            if cursor == 0:
                break
        return n

    def delete(self, chat_id: str) -> bool:
        return bool(self._client.delete(self._key(chat_id)))

    def _write(self, session: SessionData) -> None:
        data = json.dumps(session.to_dict(), ensure_ascii=False, default=str)
        self._client.setex(
            self._key(session.chat_id),
            self._max_age,
            data,
        )
