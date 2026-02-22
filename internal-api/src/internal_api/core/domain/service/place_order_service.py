from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from returns.pipeline import flow
from returns.pointfree import bind, map_
from returns.result import Failure, Result, Success

from internal_api.core.domain.model.errors import PlaceOrderError, ValidationError
from internal_api.core.domain.model.order import (
    CustomerId,
    LineItem,
    Money,
    Order,
    OrderId,
    Sku,
    now_utc,
)
from internal_api.core.ports.inbound.place_order import (
    OrderReceipt,
    PlaceOrderCommand,
    PlaceOrderUseCase,
)
from internal_api.core.ports.outbound.events import EventPublisher, OrderPlaced
from internal_api.core.ports.outbound.inventory import InventoryGateway, Reservation
from internal_api.core.ports.outbound.orders import OrderRepository
from internal_api.core.ports.outbound.payment import ChargeRequest, PaymentGateway


@dataclass(frozen=True)
class PlaceOrderDeps:
    inventory: InventoryGateway
    payment: PaymentGateway
    orders: OrderRepository
    events: EventPublisher


@dataclass(frozen=True)
class PlaceOrderContext:
    order: Order
    payment_token: str


@dataclass(frozen=True)
class PlaceOrderService(PlaceOrderUseCase):
    deps: PlaceOrderDeps

    def place_order(
        self, command: PlaceOrderCommand
    ) -> Result[OrderReceipt, PlaceOrderError]:
        return flow(
            command,
            _validate_command,
            bind(_build_context),
            bind(self._reserve_inventory),
            bind(self._charge_payment),
            bind(self._persist),
            bind(self._publish),
            map_(_to_receipt),
        )

    def _reserve_inventory(
        self, ctx: PlaceOrderContext
    ) -> Result[PlaceOrderContext, PlaceOrderError]:
        reservations = tuple(Reservation(li.sku, li.quantity) for li in ctx.order.items)
        return self.deps.inventory.reserve(reservations).map(lambda _: ctx)

    def _charge_payment(
        self, ctx: PlaceOrderContext
    ) -> Result[PlaceOrderContext, PlaceOrderError]:
        req = ChargeRequest(
            ctx.order.customer_id, ctx.order.total(), token=ctx.payment_token
        )
        return self.deps.payment.charge(req).map(lambda _: ctx)

    def _persist(
        self, ctx: PlaceOrderContext
    ) -> Result[PlaceOrderContext, PlaceOrderError]:
        return self.deps.orders.save(ctx.order).map(lambda _: ctx)

    def _publish(
        self, ctx: PlaceOrderContext
    ) -> Result[PlaceOrderContext, PlaceOrderError]:
        return self.deps.events.publish(OrderPlaced(ctx.order.order_id)).map(
            lambda _: ctx
        )


def _validate_command(
    cmd: PlaceOrderCommand,
) -> Result[PlaceOrderCommand, PlaceOrderError]:
    if not cmd.customer_id.strip():
        return Failure(ValidationError("customer_id is required"))
    if not cmd.lines:
        return Failure(ValidationError("at least one line item is required"))
    if not cmd.payment_token.strip():
        return Failure(ValidationError("payment_token is required"))

    for i, ln in enumerate(cmd.lines):
        if not ln.sku.strip():
            return Failure(ValidationError(f"lines[{i}].sku is required"))
        if ln.quantity <= 0:
            return Failure(ValidationError(f"lines[{i}].quantity must be > 0"))
        if Decimal(ln.unit_price) <= 0:
            return Failure(ValidationError(f"lines[{i}].unit_price must be > 0"))

    return Success(cmd)


def _build_context(
    cmd: PlaceOrderCommand,
) -> Result[PlaceOrderContext, PlaceOrderError]:
    items: Tuple[LineItem, ...] = tuple(
        LineItem(
            sku=Sku(ln.sku),
            unit_price=Money.of(ln.unit_price),
            quantity=ln.quantity,
        )
        for ln in cmd.lines
    )
    order = Order(
        order_id=OrderId.new(),
        customer_id=CustomerId(cmd.customer_id),
        items=items,
        created_at=now_utc(),
    )
    return Success(PlaceOrderContext(order=order, payment_token=cmd.payment_token))


def _to_receipt(ctx: PlaceOrderContext) -> OrderReceipt:
    return OrderReceipt(
        order_id=ctx.order.order_id,
        customer_id=ctx.order.customer_id,
        total=ctx.order.total(),
    )
