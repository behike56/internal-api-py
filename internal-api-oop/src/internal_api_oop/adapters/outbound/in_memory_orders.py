from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Sequence

from returns.result import Failure, Result, Success

from internal_api_oop.core.domain.model.errors import (
    OrderNotFound,
    PersistenceError,
    PlaceOrderError,
)
from internal_api_oop.core.domain.model.order import CustomerId, Order, OrderId
from internal_api_oop.core.ports.outbound.orders import OrderRepository


@dataclass
class InMemoryOrderRepository(OrderRepository):
    _store: Dict[str, Order] = field(default_factory=dict)

    def save(self, order: Order) -> Result[OrderId, PlaceOrderError]:
        key = str(order.order_id.value)
        if key in self._store:
            return Failure(PersistenceError(message="order_id already exists"))
        self._store[key] = order
        return Success(order.order_id)

    def get(self, order_id: OrderId) -> Result[Order, PlaceOrderError]:
        key = str(order_id.value)
        if key not in self._store:
            return Failure(OrderNotFound(message="order not found", order_id=key))
        return Success(self._store[key])

    def list(
        self,
        offset: int,
        limit: int,
        customer_id: CustomerId | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> Result[Sequence[Order], PlaceOrderError]:
        orders = list(self._store.values())  # insertion order

        if customer_id is not None:
            orders = [o for o in orders if o.customer_id.value == customer_id.value]

        reverse = sort_dir == "desc"

        if sort_by == "created_at":
            orders = sorted(orders, key=lambda o: o.created_at, reverse=reverse)
        elif sort_by == "total":
            orders = sorted(orders, key=lambda o: o.total().amount, reverse=reverse)

        sliced = orders[offset : offset + limit]
        return Success(tuple(sliced))
