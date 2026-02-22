from __future__ import annotations

from dataclasses import dataclass

from returns.result import Failure, Result, Success

from internal_api.core.domain.model.errors import PlaceOrderError, PublishError
from internal_api.core.ports.outbound.events import EventPublisher, OrderPlaced


@dataclass
class StdoutEventPublisher(EventPublisher):
    fail: bool = False

    def publish(self, event: OrderPlaced) -> Result[None, PlaceOrderError]:
        if self.fail:
            return Failure(PublishError(message="publisher is down"))
        print(f"[event] order_placed: {event.order_id.value}")
        return Success(None)
