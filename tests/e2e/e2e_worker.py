"""LOCAL TEST-ONLY worker for the browser E2E stack: the real worker loop (lfhe_orchestrator.worker.make_handlers +
lfhe_shared.jobs.JobQueue, lease / retry / completion semantics unchanged) with the SYNTHETIC_TEST_ONLY scripted model
(synthetic_provider.responder) instead of a provider, and a local object store for the release PDF."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tests", ROOT / "tests" / "integration", ROOT / "tests" / "e2e"):
    sys.path.insert(0, str(p))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from lfhe_orchestrator.providers import FakeProvider  # noqa: E402
from lfhe_orchestrator.worker import make_handlers  # noqa: E402
from lfhe_shared.jobs import JobQueue  # noqa: E402
from lfhe_shared.storage import LocalObjectStore  # noqa: E402
from synthetic_provider import responder  # noqa: E402

STOP = False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--store", required=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    def stop(*_):
        global STOP
        STOP = True
    signal.signal(signal.SIGTERM, stop)
    mc = args.config
    with psycopg.connect(args.db, autocommit=True, row_factory=dict_row) as conn:
        q = JobQueue(conn, "e2e-synthetic-worker")
        handlers = make_handlers(conn, q, FakeProvider(responder), m02_config=mc, m03_config=mc, worker_id="e2e-synthetic-worker",
                                 m04_config=mc, m05_config=mc, m06_config=mc, m07_config=mc, m08_config=mc, m09_config=mc,
                                 m10_config=mc, store=LocalObjectStore(Path(args.store)))
        while not STOP:
            if q.run_once(handlers, limit=1) == 0:
                time.sleep(0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
