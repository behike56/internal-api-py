from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from returns.result import Result

from internal_api.core.domain.model.errors import PlaceOrderError
from internal_api.core.domain.model.order import OrderId


@dataclass(frozen=True)
class OrderPlaced:
    order_id: OrderId


class EventPublisher(Protocol):
    def publish(self, event: OrderPlaced) -> Result[None, PlaceOrderError]: ...
