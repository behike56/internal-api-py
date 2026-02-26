from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "internal_api_fp.bootstrap:create_asgi_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
