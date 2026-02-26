from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ValidationError(OrderError):
    pass


@dataclass(frozen=True)
class PersistenceError(OrderError):
    pass


@dataclass(frozen=True)
class PublishError(OrderError):
    pass
