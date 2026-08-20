"""Run the retention purge from cron/systemd on-site (§9).

    python -m scripts.purge_retention            # use configured retention_days
    python -m scripts.purge_retention --days 14  # override the window
"""

from __future__ import annotations

import argparse
import asyncio
import json

from src.common.config import get_settings
from src.common.logging import setup_logging
from src.storage.db import init_db
from src.storage.retention import run_retention_purge


async def _run(days: int | None) -> dict:
    await init_db(get_settings().db_url)
    return await run_retention_purge(days)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="override retention window")
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)
    result = asyncio.run(_run(args.days))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
