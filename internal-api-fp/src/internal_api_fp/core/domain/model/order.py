from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Tuple
from uuid import UUID, uuid4


@dataclass(frozen=True)
class OrderId:
    value: UUID

    @staticmethod
    def new() -> "OrderId":
        return OrderId(uuid4())


@dataclass(frozen=True)
class CustomerId:
    value: str


@dataclass(frozen=True)
class Sku:
    value: str


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "JPY"

    @staticmethod
    def of(amount: Decimal | int | str, currency: str = "JPY") -> "Money":
        dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(dec, currency)

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, n: int) -> "Money":
        return Money(
            (self.amount * Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            self.currency,
        )

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency_mismatch: {self.currency} vs {other.currency}")


@dataclass(frozen=True)
class LineItem:
    sku: Sku
    unit_price: Money
    quantity: int

    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Order:
    order_id: OrderId
    customer_id: CustomerId
    items: Tuple[LineItem, ...]
    created_at: datetime

    def total(self) -> Money:
        return fold_money((it.subtotal() for it in self.items), currency="JPY")


def fold_money(values: Iterable[Money], currency: str = "JPY") -> Money:
    total = Money.of(0, currency=currency)
    for v in values:
        total = total + v
    return total


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
