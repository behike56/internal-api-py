from __future__ import annotations

from decimal import Decimal

from returns.result import Failure, Result, Success

from internal_api_fp.core.domain.model.errors import OrderError, ValidationError
from internal_api_fp.core.ports.inbound.place_order import PlaceOrderCommand


def validate_customer_id(cmd: PlaceOrderCommand) -> Result[PlaceOrderCommand, OrderError]:
    if not cmd.customer_id.strip():
        return Failure(ValidationError("customer_id is required"))
    return Success(cmd)


def validate_items(cmd: PlaceOrderCommand) -> Result[PlaceOrderCommand, OrderError]:
    if not cmd.lines:
        return Failure(ValidationError("at least one line item is required"))
    for i, ln in enumerate(cmd.lines):
        if not ln.sku.strip():
            return Failure(ValidationError(f"lines[{i}].sku is required"))
        if ln.quantity <= 0:
            return Failure(ValidationError(f"lines[{i}].quantity must be > 0"))
        if Decimal(str(ln.unit_price)) <= 0:
            return Failure(ValidationError(f"lines[{i}].unit_price must be > 0"))
    return Success(cmd)


def validate_command(cmd: PlaceOrderCommand) -> Result[PlaceOrderCommand, OrderError]:
    return Success(cmd).bind(validate_customer_id).bind(validate_items)
