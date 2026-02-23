from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from returns.result import Result

from internal_api_oop.core.domain.model.errors import PlaceOrderError
from internal_api_oop.core.domain.model.order import Sku


@dataclass(frozen=True)
class Reservation:
    sku: Sku
    quantity: int


class InventoryGateway(Protocol):
    def reserve(
        self, reservations: Sequence[Reservation]
    ) -> Result[None, PlaceOrderError]: ...
