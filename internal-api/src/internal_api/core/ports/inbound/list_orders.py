from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from returns.result import Result

from internal_api.core.domain.model.errors import PlaceOrderError
from internal_api.core.domain.model.order import CustomerId, Money, OrderId


@dataclass(frozen=True)
class ListOrdersQuery:
    offset: int = 0
    limit: int = 50
    customer_id: str | None = None
    sort_by: str = "created_at"  # created_at | total
    sort_dir: str = "desc"  # asc | desc


@dataclass(frozen=True)
class OrderSummaryView:
    order_id: OrderId
    customer_id: CustomerId
    total: Money


class ListOrdersUseCase(Protocol):
    def list_orders(
        self, query: ListOrdersQuery
    ) -> Result[Sequence[OrderSummaryView], PlaceOrderError]: ...
