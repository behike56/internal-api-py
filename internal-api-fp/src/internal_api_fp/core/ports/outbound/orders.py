from __future__ import annotations

from typing import Callable

from returns.io import IOResult

from internal_api_fp.core.domain.model.errors import OrderError
from internal_api_fp.core.domain.model.order import Order, OrderId

SaveOrder = Callable[[Order], IOResult[None, OrderError]]
FindOrder = Callable[[OrderId], IOResult[Order, OrderError]]
