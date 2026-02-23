from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceOrderError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


@dataclass(frozen=True)
class ValidationError(PlaceOrderError):
    pass


@dataclass(frozen=True)
class OutOfStock(PlaceOrderError):
    sku: str

    def __str__(self) -> str:  # pragma: no cover
        return f"out_of_stock: sku={self.sku} ({self.message})"


@dataclass(frozen=True)
class PaymentDeclined(PlaceOrderError):
    reason: str

    def __str__(self) -> str:  # pragma: no cover
        return f"payment_declined: {self.reason} ({self.message})"


@dataclass(frozen=True)
class PersistenceError(PlaceOrderError):
    pass


@dataclass(frozen=True)
class OrderNotFound(PersistenceError):
    order_id: str

    def __str__(self) -> str:  # pragma: no cover
        return f"order_not_found: {self.order_id} ({self.message})"


@dataclass(frozen=True)
class PublishError(PlaceOrderError):
    pass


@dataclass(frozen=True)
class IdempotencyInProgress(PlaceOrderError):
    key: str

    def __str__(self) -> str:  # pragma: no cover
        return f"idempotency_in_progress: {self.key} ({self.message})"


@dataclass(frozen=True)
class IdempotencyFailed(PlaceOrderError):
    key: str
    previous_error: str

    def __str__(self) -> str:  # pragma: no cover
        return f"idempotency_failed: {self.key} prev={self.previous_error} ({self.message})"


@dataclass(frozen=True)
class IdempotencyKeyConflict(PlaceOrderError):
    key: str

    def __str__(self) -> str:  # pragma: no cover
        return f"idempotency_key_conflict: {self.key} ({self.message})"
