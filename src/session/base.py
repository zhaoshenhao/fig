from abc import ABC, abstractmethod

from src.session.data import SessionData


class SessionStore(ABC):

    @abstractmethod
    def get(self, chat_id: str) -> SessionData | None: ...

    @abstractmethod
    def create(self, workflow_name: str, return_mode: str) -> SessionData: ...

    @abstractmethod
    def save(self, session: SessionData) -> None: ...

    @abstractmethod
    def delete(self, chat_id: str) -> bool: ...

    @abstractmethod
    def count(self) -> int: ...
