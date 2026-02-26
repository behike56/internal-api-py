from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from internal_api_fp.core.domain.model.order import CustomerId, Money, OrderId


@dataclass(frozen=True)
class PlaceOrderLine:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass(frozen=True)
class PlaceOrderCommand:
    customer_id: str
    lines: tuple[PlaceOrderLine, ...]


@dataclass(frozen=True)
class OrderReceipt:
    order_id: OrderId
    customer_id: CustomerId
    total: Money
