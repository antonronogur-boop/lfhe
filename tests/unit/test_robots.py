"""CG1-07 — robots.txt fails closed; temporary failures never poison the cache."""
import httpx
import pytest

from lfhe_collector.http import (DestinationRefused, PoliteHttpClient, RobotsDisallowed,
                                 SourceUnavailable)

ARTICLE = "https://news.example.org/a/article.html"
HTML = {"content-type": "text/html; charset=utf-8"}


class Site:
    """Programmable robots.txt behaviour; logs every request path."""

    def __init__(self, robots):
        self.robots = robots          # callable(request) -> httpx.Response, or Response
        self.log: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.log.append(f"{request.url.host}{request.url.path}")
        if request.url.path == "/robots.txt":
            r = self.robots
            return r(request) if callable(r) else r
        if request.url.path == "/moved-robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /a/\n")
        return httpx.Response(200, headers=HTML, content=b"<p>synthetic article</p>")

    def article_requests(self):
        return sum(1 for p in self.log if p.endswith("/a/article.html"))

    def robots_requests(self):
        return sum(1 for p in self.log if p.endswith("robots.txt"))


def client(site, **kw):
    return PoliteHttpClient("LFHE-Test/0.1", min_interval=0, allow_private_hosts=True,
                            transport=httpx.MockTransport(site.handler), **kw)


def test_1_robots_200_allow():
    site = Site(httpx.Response(200, text="User-agent: *\nDisallow: /private/\n"))
    assert client(site).get(ARTICLE).status_code == 200
    assert site.article_requests() == 1


def test_2_robots_200_disallow():
    site = Site(httpx.Response(200, text="User-agent: *\nDisallow: /a/\n"))
    with pytest.raises(RobotsDisallowed):
        client(site).get(ARTICLE)
    assert site.article_requests() == 0


@pytest.mark.parametrize("status", [401, 403])
def test_3_4_robots_access_controlled_fails_closed(status):
    site = Site(httpx.Response(status))
    with pytest.raises(RobotsDisallowed):
        client(site).get(ARTICLE)
    assert site.article_requests() == 0


@pytest.mark.parametrize("status", [404, 410])
def test_5_robots_absent_means_no_policy(status):
    site = Site(httpx.Response(status))
    assert client(site).get(ARTICLE).status_code == 200


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_6_7_robots_temporarily_unavailable_is_retryable_and_target_not_fetched(status):
    site = Site(httpx.Response(status))
    c = client(site)
    with pytest.raises(SourceUnavailable) as exc:
        c.get(ARTICLE)
    assert exc.value.retryable is True
    assert site.article_requests() == 0


@pytest.mark.parametrize("status", [400, 405, 451])
def test_other_client_errors_fail_closed(status):
    site = Site(httpx.Response(status))
    with pytest.raises(RobotsDisallowed):
        client(site).get(ARTICLE)
    assert site.article_requests() == 0


def test_8_network_failure_then_recovery_same_client():
    state = {"fail": True}

    def robots(request):
        if state["fail"]:
            raise httpx.ConnectError("synthetic network failure", request=request)
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    site = Site(robots)
    c = client(site, robots_failure_ttl=0)  # job backoff ≥ 1 min > default failure TTL (60 s)
    with pytest.raises(SourceUnavailable):
        c.get(ARTICLE)
    assert site.article_requests() == 0
    state["fail"] = False
    assert c.get(ARTICLE).status_code == 200, "same client recovers: failure was not cached permanently"
    assert site.robots_requests() == 2 and site.article_requests() == 1


def test_failure_is_cached_only_for_the_failure_ttl():
    site = Site(httpx.Response(503))
    c = client(site, robots_failure_ttl=3600)
    for _ in range(3):
        with pytest.raises(SourceUnavailable):
            c.get(ARTICLE)
    assert site.robots_requests() == 1, "within the failure TTL robots.txt is not hammered"
    c.robots_failure_ttl = 0
    c._robots.clear()  # simulate TTL expiry
    site.robots = httpx.Response(200, text="")
    assert c.get(ARTICLE).status_code == 200


def test_successful_policy_is_cached():
    site = Site(httpx.Response(200, text="User-agent: *\nAllow: /\n"))
    c = client(site)
    c.get(ARTICLE)
    c.get(ARTICLE)
    assert site.robots_requests() == 1


def test_9_robots_redirect_followed_under_destination_rules():
    site = Site(httpx.Response(301, headers={"location": "/moved-robots.txt"}))
    with pytest.raises(RobotsDisallowed):  # moved robots.txt disallows /a/
        client(site).get(ARTICLE)
    assert site.article_requests() == 0 and "news.example.org/moved-robots.txt" in site.log


@pytest.mark.parametrize("redirect,expected", [
    (httpx.Response(302), SourceUnavailable),                                       # no Location
    (httpx.Response(302, headers={"location": "/robots.txt"}), SourceUnavailable),  # loop → too many hops
    (httpx.Response(302, headers={"location": "file:///etc/passwd"}), DestinationRefused),
])
def test_9b_malformed_or_unsafe_robots_redirect_never_allows(redirect, expected):
    site = Site(redirect)
    with pytest.raises(expected):
        client(site).get(ARTICLE)
    assert site.article_requests() == 0


def test_9c_robots_redirect_to_private_address_refused():
    site = Site(httpx.Response(302, headers={"location": "http://127.0.0.1/robots.txt"}))
    c = PoliteHttpClient("LFHE-Test/0.1", min_interval=0, allow_private_hosts=False,
                         transport=httpx.MockTransport(site.handler))
    c._check_destination = _public_only(c._check_destination)
    with pytest.raises(DestinationRefused):
        c.get(ARTICLE)
    assert site.article_requests() == 0


def _public_only(original):
    """Treat *.example.org as public (no DNS in tests); everything else uses the real rule."""
    def check(url):
        if "example.org" in url:
            return None
        return original(url)
    return check


def test_10_oversized_robots_fails_closed():
    site = Site(httpx.Response(200, text="User-agent: *\n" + "#" * 300_000))
    with pytest.raises(RobotsDisallowed):
        client(site, max_bytes=200_000).get(ARTICLE)
    assert site.article_requests() == 0
