from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from returns.result import Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError
from internal_api_oop.core.domain.model.order import CustomerId, Money, OrderId


@dataclass(frozen=True)
class GetOrderQuery:
    order_id: str  # UUID string


@dataclass(frozen=True)
class OrderLineView:
    sku: str
    unit_price: Money
    quantity: int
    subtotal: Money


@dataclass(frozen=True)
class OrderView:
    order_id: OrderId
    customer_id: CustomerId
    total: Money
    lines: Sequence[OrderLineView]


class GetOrderUseCase(Protocol):
    def get_order(self, query: GetOrderQuery) -> Result[OrderView, PlaceOrderError]: ...
