from __future__ import annotations

from typing import Protocol, Sequence

from returns.result import Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError
from internal_api_oop.core.domain.model.order import CustomerId, Order, OrderId


class OrderRepository(Protocol):
    def save(self, order: Order) -> Result[OrderId, PlaceOrderError]: ...

    def get(self, order_id: OrderId) -> Result[Order, PlaceOrderError]: ...

    def list(
        self,
        offset: int,
        limit: int,
        customer_id: CustomerId | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> Result[Sequence[Order], PlaceOrderError]: ...
