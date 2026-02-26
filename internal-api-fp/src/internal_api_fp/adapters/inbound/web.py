from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from returns.io import IOSuccess

from internal_api_fp.core.domain.model.errors import (
    OrderError,
    PersistenceError,
    PublishError,
    ValidationError,
)
from internal_api_fp.core.ports.inbound.place_order import (
    OrderReceipt,
    PlaceOrderCommand,
    PlaceOrderLine,
)


# ---- HTTP DTOs -------------------------------------------------------------


class PlaceOrderLineIn(BaseModel):
    sku: str = Field(min_length=1, examples=["SKU-A"])
    unit_price: Decimal = Field(gt=0, examples=["1500.00"])
    quantity: int = Field(gt=0, examples=[2])


class PlaceOrderRequest(BaseModel):
    customer_id: str = Field(min_length=1, examples=["cust-001"])
    lines: list[PlaceOrderLineIn] = Field(min_length=1)


class OrderReceiptResponse(BaseModel):
    order_id: str
    customer_id: str
    total: str
    currency: str


class ErrorResponse(BaseModel):
    type: str
    message: str


# ---- Mapping helpers -------------------------------------------------------


def _to_command(req: PlaceOrderRequest) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        customer_id=req.customer_id,
        lines=tuple(
            PlaceOrderLine(sku=ln.sku, unit_price=ln.unit_price, quantity=ln.quantity)
            for ln in req.lines
        ),
    )


def _to_response(receipt: OrderReceipt) -> dict:
    return OrderReceiptResponse(
        order_id=str(receipt.order_id.value),
        customer_id=receipt.customer_id.value,
        total=str(receipt.total.amount),
        currency=receipt.total.currency,
    ).model_dump()


def _to_http_error(err: OrderError) -> tuple[int, dict]:
    if isinstance(err, ValidationError):
        status = 400
    elif isinstance(err, PublishError):
        status = 503
    elif isinstance(err, PersistenceError):
        status = 500
    else:
        status = 500
    return status, ErrorResponse(type=type(err).__name__, message=str(err)).model_dump()


# ---- App factory -----------------------------------------------------------


def create_fastapi_app(handle_place_order: Callable) -> FastAPI:
    app = FastAPI(title="internal_api_fp")

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(type="RequestValidationError", message="invalid request")
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(type=type(exc).__name__, message="internal server error")
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/orders", status_code=201)
    def place_order_endpoint(req: PlaceOrderRequest) -> Any:
        cmd = _to_command(req)
        io_result = handle_place_order(cmd)
        if isinstance(io_result, IOSuccess):
            receipt: OrderReceipt = io_result._inner_value.unwrap()
            return _to_response(receipt)
        err: OrderError = io_result._inner_value.failure()
        status, body = _to_http_error(err)
        return JSONResponse(status_code=status, content=body)

    return app
