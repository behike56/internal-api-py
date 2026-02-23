from __future__ import annotations

from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from internal_api.core.domain.model.errors import PersistenceError, PlaceOrderError
from internal_api.core.domain.model.idempotency import IdempotencyRecord
from internal_api.core.domain.model.order import CustomerId, OrderId, now_utc
from internal_api.core.ports.outbound.idempotency import IdempotencyRepository


@dataclass
class InMemoryIdempotencyRepository(IdempotencyRepository):
    _store: dict[tuple[str, str], IdempotencyRecord] = field(default_factory=dict)

    def get(
        self, customer_id: CustomerId, key: str
    ) -> Result[IdempotencyRecord | None, PlaceOrderError]:
        return Success(self._store.get((customer_id.value, key)))

    def start(
        self, customer_id: CustomerId, key: str, order_id: OrderId, request_hash: str
    ) -> Result[None, PlaceOrderError]:
        k = (customer_id.value, key)
        if k in self._store:
            return Failure(PersistenceError(message="idempotency key already exists"))

        now = now_utc()
        self._store[k] = IdempotencyRecord(
            status="IN_PROGRESS",
            order_id=order_id,
            request_hash=request_hash,
            started_at=now,
            updated_at=now,
            previous_error=None,
            response_snapshot_json=None,
        )
        return Success(None)

    def complete(
        self, customer_id: CustomerId, key: str, response_snapshot_json: str
    ) -> Result[None, PlaceOrderError]:
        k = (customer_id.value, key)
        rec = self._store.get(k)
        if rec is None:
            return Failure(PersistenceError(message="idempotency key missing"))

        now = now_utc()
        self._store[k] = IdempotencyRecord(
            status="COMPLETED",
            order_id=rec.order_id,
            request_hash=rec.request_hash,
            started_at=rec.started_at,
            updated_at=now,
            previous_error=rec.previous_error,
            response_snapshot_json=response_snapshot_json,
        )
        return Success(None)

    def fail(
        self, customer_id: CustomerId, key: str, previous_error: str
    ) -> Result[None, PlaceOrderError]:
        k = (customer_id.value, key)
        rec = self._store.get(k)
        if rec is None:
            return Failure(PersistenceError(message="idempotency key missing"))

        now = now_utc()
        self._store[k] = IdempotencyRecord(
            status="FAILED",
            order_id=rec.order_id,
            request_hash=rec.request_hash,
            started_at=rec.started_at,
            updated_at=now,
            previous_error=previous_error,
            response_snapshot_json=rec.response_snapshot_json,
        )
        return Success(None)
