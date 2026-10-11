# Collection outcome semantics (CG1-01, CG1-04)

## Item failure classes

| Class | Codes | Retry? |
| --- | --- | --- |
| RETRYABLE | `SOURCE_UNAVAILABLE` (network error, timeout, HTTP 429, HTTP 5xx, robots.txt temporarily unreachable, too many redirects), `STORE_FAILED` (database / object-store error) | yes, bounded by `max_attempts` |
| NON_RETRYABLE | `ACCESS_DENIED` (401, 402, 403), `ROBOTS_DISALLOWED`, `CONTENT_REJECTED` (type/size/other 4xx), `DESTINATION_REFUSED` | never |
| Policy skip (not a failure) | `EXTERNAL_LINK_SKIPPED`, `EXTERNAL_REDIRECT_REJECTED`, `PERMANENT_FAILURE_NOT_RETRIED` | never |

## Run status and job decision (`lfhe_collector.collector.classify_run`)

| Situation (over attempted items) | Run status | Job |
| --- | --- | --- |
| no failures | `SUCCESS` | done |
| some succeeded, some failed | `PARTIAL` | done — no job retry; the next scheduled run re-attempts |
| all failed, all transient | `SOURCE_UNAVAILABLE` | retry with backoff |
| all failed, all permanent | `FAILED` | **permanent failure, no retry** |
| all failed, mixed | `FAILED` | retry — only the transient items are re-attempted |

Within one job, every retry skips URLs that failed permanently in an earlier
attempt of that job (`permanent_failure_urls` in the run details →
`PERMANENT_FAILURE_NOT_RETRIED`). An access-controlled page is therefore
requested at most once per job, never repeatedly through job-level retry.
Discovery-level failures keep their existing rule: feed/API unreachable →
retry; feed/API access denied or invalid configuration → permanent.

Limitation: a later *scheduled* collection (a new job) will request a
previously denied item again if the feed still lists it — once per schedule
interval, never in a retry loop.

## Redirects and source domain

With `allow_external_links = false` (default):
* the discovered URL must be inside the source's `canonical_domain` (exact host
  or subdomain), otherwise `EXTERNAL_LINK_SKIPPED`;
* every redirect hop is checked **before** it is requested; a hop leaving the
  domain stops the chain with `EXTERNAL_REDIRECT_REJECTED` — the external host
  is never contacted and nothing is stored;
* `lfhe.record_snapshot` independently refuses a snapshot whose final URL host
  is outside the domain (`EXTERNAL_ORIGIN_NOT_ALLOWED`).

With `allow_external_links = true`, the document is stored and its external
origin is explicit: `article_snapshots.final_origin_host` (generated from
`final_url`), `final_url_in_source_domain = false`, and `final_url` is part of
the snapshot source state. Later lineage processing must treat such documents
as originating from that external host, not from the source.

## robots.txt (CG1-07)

| robots.txt response | Outcome | Target document requested? | Cached |
| --- | --- | --- | --- |
| 2xx | parsed; rules applied | only if allowed | 24 h (`robots_cache_ttl`) |
| 401, 403 | disallow all (`ROBOTS_DISALLOWED`, permanent) | no | 24 h |
| 404, 410 | no policy → allow (RFC 9309 §2.3.1.3) | yes | 24 h |
| other 4xx (400, 405, 451, …) | disallow all — conservative, documented deviation from RFC 9309 | no | 24 h |
| 429, 5xx | `SOURCE_UNAVAILABLE` (retryable) | **no** | failure TTL only (60 s) |
| network error / timeout | `SOURCE_UNAVAILABLE` (retryable) | **no** | failure TTL only (60 s) |
| 3xx | followed up to 5 hops, each hop through the same destination (SSRF) checks | after a final answer only | as final answer |
| 3xx without Location, > 5 hops, other status | `SOURCE_UNAVAILABLE` (retryable) — never allow-all | no | failure TTL only |
| 3xx to a refused destination (scheme / private address) | `DESTINATION_REFUSED` (permanent) | no | not cached |
| body larger than `max_bytes` | disallow all | no | 24 h |

A temporary robots failure is remembered for at most `robots_failure_ttl`
(default 60 s, shorter than the minimum job backoff of 1 min), so a later job
attempt using the same long-running client retrieves robots.txt again and
recovers. robots.txt is checked for every redirect hop of the target document.
