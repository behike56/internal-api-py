from __future__ import annotations

from internal_api_oop.adapters.inbound.web.fastapi_app import create_app
from internal_api_oop.bootstrap import build_usecases

usecases = build_usecases()
app = create_app(usecases.place_order, usecases.get_order, usecases.list_orders)
