from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from returns.result import Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError
from internal_api_oop.core.domain.model.order import CustomerId, Money, OrderId


@dataclass(frozen=True)
class PlaceOrderLine:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass(frozen=True)
class PlaceOrderCommand:
    customer_id: str
    lines: Sequence[PlaceOrderLine]
    payment_token: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class OrderReceipt:
    order_id: OrderId
    customer_id: CustomerId
    total: Money


class PlaceOrderUseCase(Protocol):
    def place_order(
        self, command: PlaceOrderCommand
    ) -> Result[OrderReceipt, PlaceOrderError]: ...
