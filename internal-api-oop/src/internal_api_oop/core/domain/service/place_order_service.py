from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from decimal import Decimal as D
from typing import Callable, Tuple
from uuid import UUID

from returns.pipeline import flow
from returns.pointfree import bind, map_
from returns.result import Failure, Result, Success

from internal_api_oop.core.domain.model.errors import (
    IdempotencyFailed,
    IdempotencyInProgress,
    IdempotencyKeyConflict,
    PlaceOrderError,
    ValidationError,
)
from internal_api_oop.core.domain.model.idempotency import IdempotencyRecord
from internal_api_oop.core.domain.model.order import (
    CustomerId,
    LineItem,
    Money,
    Order,
    OrderId,
    Sku,
    now_utc,
)
from internal_api_oop.core.ports.inbound.place_order import (
    OrderReceipt,
    PlaceOrderCommand,
    PlaceOrderUseCase,
)
from internal_api_oop.core.ports.outbound.events import EventPublisher, OrderPlaced
from internal_api_oop.core.ports.outbound.idempotency import IdempotencyRepository
from internal_api_oop.core.ports.outbound.inventory import InventoryGateway, Reservation
from internal_api_oop.core.ports.outbound.orders import OrderRepository
from internal_api_oop.core.ports.outbound.payment import ChargeRequest, PaymentGateway

Finalize = tuple[Callable[[OrderReceipt], None], Callable[[PlaceOrderError], None]]


@dataclass(frozen=True)
class PlaceOrderDeps:
    inventory: InventoryGateway
    payment: PaymentGateway
    orders: OrderRepository
    events: EventPublisher
    idempotency: IdempotencyRepository
    idempotency_ttl_seconds: int = 120  # IN_PROGRESS の寿命（例）


@dataclass(frozen=True)
class PlaceOrderContext:
    order: Order
    payment_token: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PlaceOrderService(PlaceOrderUseCase):
    deps: PlaceOrderDeps

    def place_order(
        self, command: PlaceOrderCommand
    ) -> Result[OrderReceipt, PlaceOrderError]:
        v = _validate_command(command)
        if isinstance(v, Failure):
            return v
        cmd = v.unwrap()

        # ---- no idempotency key: legacy behavior ---------------------------
        if cmd.idempotency_key is None:
            return self._run_once(cmd, order_id=OrderId.new(), finalize=None)

        # ---- idempotency enabled ------------------------------------------
        customer = CustomerId(cmd.customer_id)
        key = cmd.idempotency_key
        req_hash = _request_hash(cmd)

        existing = self.deps.idempotency.get(customer, key)
        if isinstance(existing, Failure):
            return existing

        rec = existing.unwrap()
        if rec is not None:
            if rec.request_hash != req_hash:
                return Failure(
                    IdempotencyKeyConflict(
                        message="same idempotency key used with different request",
                        key=key,
                    )
                )
            return self._resume(customer, cmd, rec)

        # create IN_PROGRESS
        order_id = OrderId.new()
        started = self.deps.idempotency.start(
            customer, key, order_id=order_id, request_hash=req_hash
        )
        if isinstance(started, Failure):
            # race-safe re-check
            existing2 = self.deps.idempotency.get(customer, key)
            if isinstance(existing2, Failure):
                return existing2
            rec2 = existing2.unwrap()
            if rec2 is None:
                return started
            if rec2.request_hash != req_hash:
                return Failure(
                    IdempotencyKeyConflict(
                        message="same idempotency key used with different request",
                        key=key,
                    )
                )
            return self._resume(customer, cmd, rec2)

        # run pipeline and finalize idempotency state
        def on_ok(receipt: OrderReceipt) -> None:
            snap = _receipt_snapshot_json(receipt)
            _ = self.deps.idempotency.complete(
                customer, key, response_snapshot_json=snap
            )

        def on_ng(err: PlaceOrderError) -> None:
            _ = self.deps.idempotency.fail(
                customer, key, previous_error=type(err).__name__
            )

        return self._run_once(cmd, order_id=order_id, finalize=(on_ok, on_ng))

    def _resume(
        self, customer: CustomerId, cmd: PlaceOrderCommand, rec: IdempotencyRecord
    ) -> Result[OrderReceipt, PlaceOrderError]:
        key = cmd.idempotency_key or "<missing>"

        if rec.status == "COMPLETED":
            # strongest: return snapshot (no DB dependency)
            if rec.response_snapshot_json:
                return Success(_receipt_from_snapshot_json(rec.response_snapshot_json))
            return self.deps.orders.get(rec.order_id).map(_order_to_receipt)

        if rec.status == "FAILED":
            return Failure(
                IdempotencyFailed(
                    message="previous request with same key failed; use a new idempotency key to retry",
                    key=key,
                    previous_error=rec.previous_error or "unknown",
                )
            )

        # IN_PROGRESS
        if not _is_expired(rec, ttl_seconds=self.deps.idempotency_ttl_seconds):
            return Failure(
                IdempotencyInProgress(
                    message="request with same key is in progress", key=key
                )
            )

        # expired IN_PROGRESS -> recovery:
        # 1) if order already exists, treat as completed
        got = self.deps.orders.get(rec.order_id)
        if isinstance(got, Success):
            receipt = _order_to_receipt(got.unwrap())
            snap = _receipt_snapshot_json(receipt)
            _ = self.deps.idempotency.complete(
                customer, key, response_snapshot_json=snap
            )
            return Success(receipt)

        # 2) if order does not exist, re-run with the SAME order_id.
        # NOTE: for full safety, inventory/payment should also be idempotent with a stable key.
        def on_ok(receipt: OrderReceipt) -> None:
            snap = _receipt_snapshot_json(receipt)
            _ = self.deps.idempotency.complete(
                customer, key, response_snapshot_json=snap
            )

        def on_ng(err: PlaceOrderError) -> None:
            _ = self.deps.idempotency.fail(
                customer, key, previous_error=type(err).__name__
            )

        return self._run_once(cmd, order_id=rec.order_id, finalize=(on_ok, on_ng))

    def _run_once(
        self, cmd: PlaceOrderCommand, order_id: OrderId, finalize: Finalize | None
    ) -> Result[OrderReceipt, PlaceOrderError]:
        result = flow(
            cmd,
            bind(lambda c: _build_context(c, order_id)),
            bind(self._reserve_inventory),
            bind(self._charge_payment),
            bind(self._persist),
            bind(self._publish),
            map_(_to_receipt),
        )

        if finalize is not None:
            ok, ng = finalize
            if isinstance(result, Success):
                ok(result.unwrap())
            else:
                ng(result.failure())

        return result

    # ---- side effects ------------------------------------------------------

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


# ---- pure helpers ----------------------------------------------------------


def _validate_command(
    cmd: PlaceOrderCommand,
) -> Result[PlaceOrderCommand, PlaceOrderError]:
    if not cmd.customer_id.strip():
        return Failure(ValidationError("customer_id is required"))
    if not cmd.lines:
        return Failure(ValidationError("at least one line item is required"))
    if not cmd.payment_token.strip():
        return Failure(ValidationError("payment_token is required"))
    if cmd.idempotency_key is not None and not cmd.idempotency_key.strip():
        return Failure(
            ValidationError("idempotency_key must be non-empty when provided")
        )

    for i, ln in enumerate(cmd.lines):
        if not ln.sku.strip():
            return Failure(ValidationError(f"lines[{i}].sku is required"))
        if ln.quantity <= 0:
            return Failure(ValidationError(f"lines[{i}].quantity must be > 0"))
        if Decimal(ln.unit_price) <= 0:
            return Failure(ValidationError(f"lines[{i}].unit_price must be > 0"))

    return Success(cmd)


def _build_context(
    cmd: PlaceOrderCommand, order_id: OrderId
) -> Result[PlaceOrderContext, PlaceOrderError]:
    items: Tuple[LineItem, ...] = tuple(
        LineItem(
            sku=Sku(ln.sku), unit_price=Money.of(ln.unit_price), quantity=ln.quantity
        )
        for ln in cmd.lines
    )
    order = Order(
        order_id=order_id,
        customer_id=CustomerId(cmd.customer_id),
        items=items,
        created_at=now_utc(),
    )
    return Success(
        PlaceOrderContext(
            order=order,
            payment_token=cmd.payment_token,
            idempotency_key=cmd.idempotency_key,
        )
    )


def _order_to_receipt(order: Order) -> OrderReceipt:
    return OrderReceipt(
        order_id=order.order_id, customer_id=order.customer_id, total=order.total()
    )


def _to_receipt(ctx: PlaceOrderContext) -> OrderReceipt:
    return _order_to_receipt(ctx.order)


def _request_hash(cmd: PlaceOrderCommand) -> str:
    payload = {
        "customer_id": cmd.customer_id,
        "payment_token": cmd.payment_token,
        "lines": [
            {"sku": ln.sku, "unit_price": str(ln.unit_price), "quantity": ln.quantity}
            for ln in cmd.lines
        ],
    }
    blob = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _is_expired(rec: IdempotencyRecord, ttl_seconds: int) -> bool:
    return (now_utc() - rec.started_at) > timedelta(seconds=ttl_seconds)


def _receipt_snapshot_json(r: OrderReceipt) -> str:
    payload = {
        "order_id": str(r.order_id.value),
        "customer_id": r.customer_id.value,
        "total": str(r.total.amount),
        "currency": r.total.currency,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _receipt_from_snapshot_json(s: str) -> OrderReceipt:
    obj = json.loads(s)
    return OrderReceipt(
        order_id=OrderId(UUID(obj["order_id"])),
        customer_id=CustomerId(obj["customer_id"]),
        total=Money(amount=D(obj["total"]), currency=obj["currency"]),
    )
