from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from internal_api.adapters.outbound.dummy_payment import DummyPaymentGateway
from internal_api.adapters.outbound.in_memory_inventory import InMemoryInventory
from internal_api.adapters.outbound.in_memory_orders import InMemoryOrderRepository
from internal_api.adapters.outbound.stdout_events import StdoutEventPublisher
from internal_api.core.domain.service.get_order_service import (
    GetOrderDeps,
    GetOrderService,
)
from internal_api.core.domain.service.list_orders_service import (
    ListOrdersDeps,
    ListOrdersService,
)
from internal_api.core.domain.service.place_order_service import (
    PlaceOrderDeps,
    PlaceOrderService,
)


@dataclass(frozen=True)
class UseCases:
    place_order: PlaceOrderService
    get_order: GetOrderService
    list_orders: ListOrdersService


def build_usecases() -> UseCases:
    inventory = InMemoryInventory(stock_by_sku={"SKU-1": 10, "SKU-2": 5})
    payment = DummyPaymentGateway(
        decline_tokens={"tok_declined"}, max_amount=Decimal("1000000.00")
    )
    orders = InMemoryOrderRepository()
    events = StdoutEventPublisher()

    place_order = PlaceOrderService(
        PlaceOrderDeps(
            inventory=inventory, payment=payment, orders=orders, events=events
        )
    )
    get_order = GetOrderService(GetOrderDeps(orders=orders))
    list_orders = ListOrdersService(ListOrdersDeps(orders=orders))

    return UseCases(
        place_order=place_order, get_order=get_order, list_orders=list_orders
    )


def build_place_internal_api() -> PlaceOrderService:
    # CLI 用（単体）。HTTP 用は build_usecases() 推奨
    return build_usecases().place_order
