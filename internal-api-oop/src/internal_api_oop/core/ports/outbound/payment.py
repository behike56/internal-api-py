from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from returns.result import Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError
from internal_api_oop.core.domain.model.order import CustomerId, Money


@dataclass(frozen=True)
class ChargeRequest:
    customer_id: CustomerId
    amount: Money
    token: str


class PaymentGateway(Protocol):
    def charge(self, request: ChargeRequest) -> Result[None, PlaceOrderError]: ...
