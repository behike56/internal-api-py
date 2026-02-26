from __future__ import annotations

from dataclasses import dataclass, field

from returns.io import IOFailure, IOResult, IOSuccess

from internal_api_fp.core.domain.model.errors import OrderError, PersistenceError
from internal_api_fp.core.domain.model.order import Order, OrderId


@dataclass
class InMemoryOrderStore:
    _store: dict[str, Order] = field(default_factory=dict)

    def save_order(self, order: Order) -> IOResult[None, OrderError]:
        self._store[str(order.order_id.value)] = order
        return IOSuccess(None)

    def find_order(self, order_id: OrderId) -> IOResult[Order, OrderError]:
        order = self._store.get(str(order_id.value))
        if order is not None:
            return IOSuccess(order)
        return IOFailure(PersistenceError("not found"))
