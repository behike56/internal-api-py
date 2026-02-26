from __future__ import annotations

from returns.io import IOResult, IOSuccess

from internal_api_fp.core.domain.model.errors import OrderError
from internal_api_fp.core.ports.outbound.events import OrderPlaced


def stdout_publish_event(event: OrderPlaced) -> IOResult[None, OrderError]:
    print(f"[event] order_placed: {event.order_id.value}")
    return IOSuccess(None)
