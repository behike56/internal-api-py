from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from returns.result import Success

from internal_api.core.ports.inbound.place_order import (
    PlaceOrderCommand,
    PlaceOrderLine,
    PlaceOrderUseCase,
)


def run_cli(usecase: PlaceOrderUseCase, raw: str) -> int:
    """
    raw: JSON string.
    Example:
      {"customer_id":"c-1","payment_token":"tok_ok",
       "lines":[{"sku":"SKU-1","unit_price":"1200.00","quantity":2}]}
    """
    try:
        payload = json.loads(raw)
        cmd = _parse_command(payload)
    except Exception as e:  # noqa: BLE001
        print(f"invalid_input: {e}")
        return 2

    result = usecase.place_order(cmd)

    if isinstance(result, Success):
        receipt = result.unwrap()
        print(
            "[ok]",
            {
                "order_id": str(receipt.order_id.value),
                "customer_id": receipt.customer_id.value,
                "total": str(receipt.total.amount),
                "currency": receipt.total.currency,
            },
        )
        return 0

    err = result.failure()
    print("[ng]", str(err))
    return 1


def _parse_command(payload: dict[str, Any]) -> PlaceOrderCommand:
    lines = [
        PlaceOrderLine(
            sku=str(x["sku"]),
            unit_price=Decimal(str(x["unit_price"])),
            quantity=int(x["quantity"]),
        )
        for x in payload.get("lines", [])
    ]
    return PlaceOrderCommand(
        customer_id=str(payload.get("customer_id", "")),
        payment_token=str(payload.get("payment_token", "")),
        lines=lines,
    )
