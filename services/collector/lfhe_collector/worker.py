"""Collector worker entry point.

    python -m lfhe_collector.worker            # run continuously
    python -m lfhe_collector.worker --once     # process one batch and exit
    python -m lfhe_collector.worker --schedule # also call enqueue_due_collections()
                                               # (only where pg_cron is not used)
"""
from __future__ import annotations

import argparse
import logging
import time

from lfhe_shared.config import load_settings
from lfhe_shared.db import connect
from lfhe_shared.jobs import JobQueue, default_worker_id
from lfhe_shared.storage import build_object_store

from .collector import make_collect_handler
from .http import PoliteHttpClient
from .snapshots import DatabaseSnapshotSink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--batch", type=int, default=5)
    parser.add_argument("--idle-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = load_settings()
    worker_id = default_worker_id()
    with connect(settings, autocommit=True) as conn, PoliteHttpClient(
        settings.collector_user_agent,
        timeout=settings.collector_timeout_seconds,
        max_bytes=settings.collector_max_bytes,
        min_interval=settings.collector_min_interval_seconds,
        respect_robots=settings.collector_respect_robots_txt,
    ) as http:
        sink = DatabaseSnapshotSink(conn, build_object_store(settings))
        queue = JobQueue(conn, worker_id)
        handlers = {"COLLECT_SOURCE": make_collect_handler(conn, http, sink, worker_id)}
        while True:
            if args.schedule:
                conn.execute("SELECT lfhe.enqueue_due_collections()")
            processed = queue.run_once(handlers, limit=args.batch)
            if args.once:
                return 0
            if processed == 0:
                time.sleep(args.idle_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
