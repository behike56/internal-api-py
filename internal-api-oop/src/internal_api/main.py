from __future__ import annotations

import sys

from internal_api.adapters.inbound.cli import run_cli
from internal_api.bootstrap import build_place_internal_api


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m internal_api.main '<json>'")
        return 2

    svc = build_place_internal_api()
    return run_cli(svc, argv[0])


if __name__ == "__main__":
    raise SystemExit(main())
