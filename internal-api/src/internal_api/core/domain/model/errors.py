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
