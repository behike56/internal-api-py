from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence

from returns.result import Failure, Result, Success

from internal_api_oop.core.domain.model.errors import OutOfStock, PlaceOrderError
from internal_api_oop.core.ports.outbound.inventory import InventoryGateway, Reservation


@dataclass
class InMemoryInventory(InventoryGateway):
    stock_by_sku: Dict[str, int]

    def reserve(
        self, reservations: Sequence[Reservation]
    ) -> Result[None, PlaceOrderError]:
        # validate first (no partial reservation)
        for r in reservations:
            available = self.stock_by_sku.get(r.sku.value, 0)
            if available < r.quantity:
                return Failure(
                    OutOfStock(message="insufficient stock", sku=r.sku.value)
                )

        # commit reservation
        for r in reservations:
            self.stock_by_sku[r.sku.value] = (
                self.stock_by_sku.get(r.sku.value, 0) - r.quantity
            )

        return Success(None)
