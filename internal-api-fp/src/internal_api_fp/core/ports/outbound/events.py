from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from returns.io import IOResult

from internal_api_fp.core.domain.model.errors import OrderError
from internal_api_fp.core.domain.model.order import OrderId


@dataclass(frozen=True)
class OrderPlaced:
    order_id: OrderId


PublishEvent = Callable[[OrderPlaced], IOResult[None, OrderError]]
