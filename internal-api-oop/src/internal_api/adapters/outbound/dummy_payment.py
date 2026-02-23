from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from returns.result import Failure, Result, Success

from internal_api.core.domain.model.errors import PaymentDeclined, PlaceOrderError
from internal_api.core.ports.outbound.payment import ChargeRequest, PaymentGateway


@dataclass
class DummyPaymentGateway(PaymentGateway):
    decline_tokens: set[str] | None = None
    max_amount: Decimal = Decimal("1000000.00")

    def charge(self, request: ChargeRequest) -> Result[None, PlaceOrderError]:
        decline = self.decline_tokens or set()
        if request.token in decline:
            return Failure(
                PaymentDeclined(message="token declined", reason="token_blacklisted")
            )
        if request.amount.amount > self.max_amount:
            return Failure(
                PaymentDeclined(message="amount too large", reason="limit_exceeded")
            )
        return Success(None)
