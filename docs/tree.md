
.
├── README.md
├── pyproject.toml
├── src
│   └── internal_api
│       ├── __init__.py
│       ├── adapters
│       │   ├── __init__.py
│       │   ├── inbound
│       │   │   ├── __init__.py
│       │   │   ├── cli.py
│       │   │   └── web
│       │   │       ├── __init__.py
│       │   │       └── fastapi_app.py
│       │   └── outbound
│       │       ├── __init__.py
│       │       ├── dummy_payment.py
│       │       ├── in_memory_idempotency.py
│       │       ├── in_memory_inventory.py
│       │       ├── in_memory_orders.py
│       │       └── stdout_events.py
│       ├── asgi.py
│       ├── bootstrap.py
│       ├── core
│       │   ├── __init__.py
│       │   ├── domain
│       │   │   ├── __init__.py
│       │   │   ├── model
│       │   │   │   ├── __init__.py
│       │   │   │   ├── errors.py
│       │   │   │   ├── idempotency.py
│       │   │   │   └── order.py
│       │   │   └── service
│       │   │       ├── __init__.py
│       │   │       ├── get_order_service.py
│       │   │       ├── list_orders_service.py
│       │   │       └── place_order_service.py
│       │   └── ports
│       │       ├── __init__.py
│       │       ├── inbound
│       │       │   ├── __init__.py
│       │       │   ├── get_order.py
│       │       │   ├── list_orders.py
│       │       │   └── place_order.py
│       │       └── outbound
│       │           ├── __init__.py
│       │           ├── events.py
│       │           ├── idempotency.py
│       │           ├── inventory.py
│       │           ├── orders.py
│       │           └── payment.py
│       └── main.py
└── uv.lock

14 directories, 39 files
