from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result

from internal_api.core.domain.model.errors import PlaceOrderError, ValidationError
from internal_api.core.domain.model.order import OrderId
from internal_api.core.ports.inbound.get_order import (
    GetOrderQuery,
    GetOrderUseCase,
    OrderLineView,
    OrderView,
)
from internal_api.core.ports.outbound.orders import OrderRepository


@dataclass(frozen=True)
class GetOrderDeps:
    orders: OrderRepository


@dataclass(frozen=True)
class GetOrderService(GetOrderUseCase):
    deps: GetOrderDeps

    def get_order(self, query: GetOrderQuery) -> Result[OrderView, PlaceOrderError]:
        try:
            oid = OrderId(UUID(query.order_id))
        except Exception:  # noqa: BLE001
            return Failure(ValidationError(message="order_id must be a valid UUID"))

        return self.deps.orders.get(oid).map(_to_view)


def _to_view(order) -> OrderView:
    lines = tuple(
        OrderLineView(
            sku=li.sku.value,
            unit_price=li.unit_price,
            quantity=li.quantity,
            subtotal=li.subtotal(),
        )
        for li in order.items
    )
    return OrderView(
        order_id=order.order_id,
        customer_id=order.customer_id,
        total=order.total(),
        lines=lines,
    )
