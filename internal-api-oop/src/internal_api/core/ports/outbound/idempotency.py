from __future__ import annotations

from typing import Protocol

from returns.result import Result

from internal_api.core.domain.model.errors import PlaceOrderError
from internal_api.core.domain.model.idempotency import IdempotencyRecord
from internal_api.core.domain.model.order import CustomerId, OrderId


class IdempotencyRepository(Protocol):
    """
    実DBでは (customer_id, key) に UNIQUE 制約を貼り、
    start/complete/fail はトランザクション内で行うのが前提。
    """

    def get(
        self, customer_id: CustomerId, key: str
    ) -> Result[IdempotencyRecord | None, PlaceOrderError]: ...

    def start(
        self, customer_id: CustomerId, key: str, order_id: OrderId
    ) -> Result[None, PlaceOrderError]:
        """キーが未登録なら IN_PROGRESS を登録（原子的であることが望ましい）。"""
        ...

    def complete(
        self, customer_id: CustomerId, key: str
    ) -> Result[None, PlaceOrderError]: ...

    def fail(
        self, customer_id: CustomerId, key: str, previous_error: str
    ) -> Result[None, PlaceOrderError]: ...
