from __future__ import annotations

from typing import Protocol

from returns.result import Result

from internal_api.core.domain.model.errors import PlaceOrderError
from internal_api.core.domain.model.idempotency import IdempotencyRecord
from internal_api.core.domain.model.order import CustomerId, OrderId


class IdempotencyRepository(Protocol):
    """
    実DBでは (customer_id, key) に UNIQUE 制約を貼り、
    start は INSERT で原子的に「最初の1件だけ勝つ」ようにする。
    """

    def get(
        self, customer_id: CustomerId, key: str
    ) -> Result[IdempotencyRecord | None, PlaceOrderError]: ...

    def start(
        self,
        customer_id: CustomerId,
        key: str,
        order_id: OrderId,
        request_hash: str,
    ) -> Result[None, PlaceOrderError]:
        """未登録なら IN_PROGRESS を登録。既に存在する場合は Failure を返す想定。"""
        ...

    def complete(
        self,
        customer_id: CustomerId,
        key: str,
        response_snapshot_json: str,
    ) -> Result[None, PlaceOrderError]: ...

    def fail(
        self,
        customer_id: CustomerId,
        key: str,
        previous_error: str,
    ) -> Result[None, PlaceOrderError]: ...
