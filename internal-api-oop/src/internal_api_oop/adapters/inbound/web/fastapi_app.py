from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from returns.result import Success

from internal_api_oop.core.domain.model.errors import (
    IdempotencyFailed,
    IdempotencyInProgress,
    IdempotencyKeyConflict,
    OrderNotFound,
    OutOfStock,
    PaymentDeclined,
    PersistenceError,
    PlaceOrderError,
    PublishError,
    ValidationError,
)
from internal_api_oop.core.ports.inbound.get_order import (
    GetOrderQuery,
    GetOrderUseCase,
)
from internal_api_oop.core.ports.inbound.list_orders import (
    ListOrdersQuery,
    ListOrdersUseCase,
)
from internal_api_oop.core.ports.inbound.place_order import (
    PlaceOrderCommand,
    PlaceOrderLine,
    PlaceOrderUseCase,
)

# ---- HTTP DTOs (adapter layer) ---------------------------------------------


class PlaceOrderLineIn(BaseModel):
    sku: str = Field(min_length=1, examples=["SKU-1"])
    unit_price: Decimal = Field(gt=0, examples=["1200.00"])
    quantity: int = Field(gt=0, examples=[2])


class PlaceOrderRequest(BaseModel):
    customer_id: str = Field(min_length=1, examples=["c-1"])
    payment_token: str = Field(min_length=1, examples=["tok_ok"])
    lines: list[PlaceOrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    sku: str
    unit_price: str
    quantity: int
    subtotal: str


class OrderReceiptResponse(BaseModel):
    order_id: str
    customer_id: str
    total: str
    currency: str


class OrderDetailsResponse(BaseModel):
    order_id: str
    customer_id: str
    total: str
    currency: str
    lines: list[OrderLineOut]


class OrderSummaryOut(BaseModel):
    order_id: str
    customer_id: str
    total: str
    currency: str


class OrderListResponse(BaseModel):
    offset: int
    limit: int
    items: list[OrderSummaryOut]


class ErrorResponse(BaseModel):
    type: str
    message: str
    details: list[dict[str, Any]] | None = None


def _map_error_to_http(err: PlaceOrderError) -> tuple[int, ErrorResponse]:
    if isinstance(err, ValidationError):
        return 400, ErrorResponse(type=type(err).__name__, message=str(err))

    if isinstance(err, OrderNotFound):
        return 404, ErrorResponse(type=type(err).__name__, message=str(err))

    if isinstance(err, OutOfStock):
        return 409, ErrorResponse(type=type(err).__name__, message=str(err))

    if isinstance(err, PaymentDeclined):
        return 402, ErrorResponse(type=type(err).__name__, message=str(err))

    if isinstance(err, PublishError):
        return 503, ErrorResponse(type=type(err).__name__, message=str(err))

    if isinstance(err, PersistenceError):
        return 500, ErrorResponse(type=type(err).__name__, message=str(err))

    return 500, ErrorResponse(type=type(err).__name__, message=str(err))


def create_app(
    place_order_uc: PlaceOrderUseCase,
    get_order_uc: GetOrderUseCase,
    list_orders_uc: ListOrdersUseCase,
) -> FastAPI:
    app = FastAPI(title="internal_api")

    # --- exception handlers (統一エラー応答) ---------------------------------

    @app.exception_handler(PlaceOrderError)
    async def handle_domain_error(_: Request, exc: PlaceOrderError) -> JSONResponse:
        status, body = _map_error_to_http(exc)
        return JSONResponse(status_code=status, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            type="RequestValidationError",
            message="invalid request",
            details=exc.errors(),
        )
        # 入力不正は 400 に寄せる
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(type=type(exc).__name__, message="internal server error")
        return JSONResponse(status_code=500, content=body.model_dump())

    # --- routes --------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/orders",
        response_model=OrderReceiptResponse,
        status_code=201,
        responses={
            400: {"model": ErrorResponse},
            402: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def place_order(
        req: PlaceOrderRequest,
        response: Response,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> Any:
        cmd = PlaceOrderCommand(
            customer_id=req.customer_id,
            payment_token=req.payment_token,
            idempotency_key=idempotency_key,
            lines=tuple(
                PlaceOrderLine(
                    sku=ln.sku,
                    unit_price=ln.unit_price,
                    quantity=ln.quantity,
                )
                for ln in req.lines
            ),
        )

        result = place_order_uc.place_order(cmd)

        if isinstance(result, Success):
            receipt = result.unwrap()
            order_id = str(receipt.order_id.value)
            response.headers["Location"] = f"/orders/{order_id}"
            return OrderReceiptResponse(
                order_id=order_id,
                customer_id=receipt.customer_id.value,
                total=str(receipt.total.amount),
                currency=receipt.total.currency,
            )

        if isinstance(
            result, (IdempotencyInProgress, IdempotencyFailed, IdempotencyKeyConflict)
        ):
            return 409, ErrorResponse(type=type(result).__name__, message=str(err))

        raise result.failure()

    @app.get(
        "/orders",
        response_model=OrderListResponse,
        responses={
            400: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    def list_orders(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        customer_id: str | None = Query(None, min_length=1),
        sort_by: str = Query("created_at"),
        sort_dir: str = Query("desc"),
    ) -> Any:
        result = list_orders_uc.list_orders(
            ListOrdersQuery(
                offset=offset,
                limit=limit,
                customer_id=customer_id,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        )

        if isinstance(result, Success):
            items = result.unwrap()
            return OrderListResponse(
                offset=offset,
                limit=limit,
                items=[
                    OrderSummaryOut(
                        order_id=str(v.order_id.value),
                        customer_id=v.customer_id.value,
                        total=str(v.total.amount),
                        currency=v.total.currency,
                    )
                    for v in items
                ],
            )

        raise result.failure()

    @app.get(
        "/orders/{order_id}",
        response_model=OrderDetailsResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    def get_order(order_id: str) -> Any:
        result = get_order_uc.get_order(GetOrderQuery(order_id=order_id))

        if isinstance(result, Success):
            view = result.unwrap()
            return OrderDetailsResponse(
                order_id=str(view.order_id.value),
                customer_id=view.customer_id.value,
                total=str(view.total.amount),
                currency=view.total.currency,
                lines=[
                    OrderLineOut(
                        sku=ln.sku,
                        unit_price=str(ln.unit_price.amount),
                        quantity=ln.quantity,
                        subtotal=str(ln.subtotal.amount),
                    )
                    for ln in view.lines
                ],
            )

        raise result.failure()

    return app
