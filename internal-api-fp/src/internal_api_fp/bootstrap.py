from __future__ import annotations

from functools import partial

from fastapi import FastAPI

from internal_api_fp.adapters.inbound.web import create_fastapi_app
from internal_api_fp.adapters.outbound.in_memory_orders import InMemoryOrderStore
from internal_api_fp.adapters.outbound.stdout_events import stdout_publish_event
from internal_api_fp.core.usecase.place_order import place_order


def build_app() -> FastAPI:
    store = InMemoryOrderStore()

    # 依存を部分適用で注入（クラスではなく関数）
    handle_place_order = partial(
        place_order,
        save_order=store.save_order,
        publish_event=stdout_publish_event,
    )
    return create_fastapi_app(handle_place_order)


def create_asgi_app() -> FastAPI:
    return build_app()
