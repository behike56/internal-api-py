from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from returns.result import Failure, Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError, ValidationError
from internal_api_oop.core.domain.model.order import CustomerId
from internal_api_oop.core.ports.inbound.list_orders import (
    ListOrdersQuery,
    ListOrdersUseCase,
    OrderSummaryView,
)
from internal_api_oop.core.ports.outbound.orders import OrderRepository


@dataclass(frozen=True)
class ListOrdersDeps:
    orders: OrderRepository


@dataclass(frozen=True)
class ListOrdersService(ListOrdersUseCase):
    deps: ListOrdersDeps

    def list_orders(
        self, query: ListOrdersQuery
    ) -> Result[Sequence[OrderSummaryView], PlaceOrderError]:
        if query.offset < 0:
            return Failure(ValidationError(message="offset must be >= 0"))
        if query.limit <= 0:
            return Failure(ValidationError(message="limit must be > 0"))
        if query.limit > 100:
            return Failure(ValidationError(message="limit must be <= 100"))

        customer: CustomerId | None = None
        if query.customer_id is not None:
            cid = query.customer_id.strip()
            if not cid:
                return Failure(
                    ValidationError(
                        message="customer_id must be non-empty when provided"
                    )
                )
            customer = CustomerId(cid)

        if query.sort_by not in {"created_at", "total"}:
            return Failure(
                ValidationError(message="sort_by must be one of: created_at, total")
            )
        if query.sort_dir not in {"asc", "desc"}:
            return Failure(ValidationError(message="sort_dir must be 'asc' or 'desc'"))

        return self.deps.orders.list(
            query.offset,
            query.limit,
            customer_id=customer,
            sort_by=query.sort_by,
            sort_dir=query.sort_dir,
        ).map(_to_summaries)


def _to_summaries(orders) -> Sequence[OrderSummaryView]:
    return tuple(
        OrderSummaryView(
            order_id=o.order_id,
            customer_id=o.customer_id,
            total=o.total(),
        )
        for o in orders
    )
