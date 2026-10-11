"""CG1-07 — robots.txt unavailability through the collector: retryable, target never
fetched, and the same long-running client recovers on the next job attempt."""
import httpx
import pytest

from conftest import make_collectable_source
from lfhe_collector.collector import collect_source
from lfhe_collector.http import PoliteHttpClient
from lfhe_shared.jobs import RetryableJobError
from test_collection import MemorySink

pytestmark = pytest.mark.db


def test_robots_503_then_recovery_through_collector(pg):
    state = {"robots": 503}
    log = []

    def handler(request):
        log.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(state["robots"], text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                              content=b"<html lang='en'><body><p>Synthetic robots recovery page.</p></body></html>")

    http = PoliteHttpClient("LFHE-Test/0.1", min_interval=0, allow_private_hosts=True, robots_failure_ttl=0,
                            transport=httpx.MockTransport(handler))
    src = make_collectable_source(pg, "HTTP_FETCH", {"urls": ["https://example.org/news/item.html"]},
                                  domain="example.org")
    with pg.worker() as c:
        with pytest.raises(RetryableJobError):
            collect_source(c, src, http, MemorySink(), worker_id="robots-test")
        run = c.execute("SELECT status, details FROM lfhe.collection_runs WHERE source_id=%s", (src["id"],)).fetchone()
        assert run["status"] == "SOURCE_UNAVAILABLE"
        assert run["details"]["item_errors"][0]["retryable"] is True
        assert "/news/item.html" not in log, "target must not be fetched while robots.txt is unavailable"

        state["robots"] = 200
        out = collect_source(c, src, http, MemorySink(), worker_id="robots-test")
    assert out.status == "SUCCESS" and out.counts["new"] == 1
    assert log.count("/robots.txt") == 2 and log.count("/news/item.html") == 1
    http.close()
