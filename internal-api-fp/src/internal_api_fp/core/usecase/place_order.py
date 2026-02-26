from __future__ import annotations

from returns.io import IOResult
from returns.result import Result, Success

from internal_api_fp.core.domain.model.errors import OrderError
from internal_api_fp.core.domain.model.order import (
    CustomerId,
    LineItem,
    Money,
    Order,
    OrderId,
    Sku,
    now_utc,
)
from internal_api_fp.core.domain.service.validation import validate_command
from internal_api_fp.core.ports.inbound.place_order import OrderReceipt, PlaceOrderCommand
from internal_api_fp.core.ports.outbound.events import OrderPlaced, PublishEvent
from internal_api_fp.core.ports.outbound.orders import SaveOrder


def _build_order(cmd: PlaceOrderCommand) -> Result[Order, OrderError]:
    """純粋：コマンド → Order（副作用なし）"""
    items = tuple(
        LineItem(Sku(l.sku), Money.of(l.unit_price), l.quantity)
        for l in cmd.lines
    )
    return Success(Order(OrderId.new(), CustomerId(cmd.customer_id), items, now_utc()))


def place_order(
    cmd: PlaceOrderCommand,
    save_order: SaveOrder,
    publish_event: PublishEvent,
) -> IOResult[OrderReceipt, OrderError]:
    # 1. 検証＋注文構築（純粋 Result）
    order_result: Result[Order, OrderError] = (
        validate_command(cmd).bind(_build_order)
    )

    # 2. IOResult に持ち上げて IO 操作を連鎖
    def persist_and_publish(order: Order) -> IOResult[OrderReceipt, OrderError]:
        return (
            save_order(order)
            .bind(lambda _: publish_event(OrderPlaced(order.order_id)))
            .map(lambda _: OrderReceipt(order.order_id, order.customer_id, order.total()))
        )

    return IOResult.from_result(order_result).bind(persist_and_publish)
