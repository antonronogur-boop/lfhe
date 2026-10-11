"""In-process HTTP server for collector tests (synthetic, topic-neutral fixtures).

Static files come from tests/fixtures/site with the placeholder ``HOST``
replaced by the server's host:port. Dynamic routes simulate failures:
  /down/...        503 Service Unavailable
  /unauthorized.html 401 (access control — must not be bypassed)
  /forbidden.html  403 (access control — must not be bypassed)
  /paywall.html    402
  /big.html        response larger than the client limit
  /binary.bin      disallowed content type
  /redirect.html   302 → /news/logistics-training-en.html
  /changing.html   content controlled by the test (revision tests)
Every request path is logged so tests can prove what was (not) fetched.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent / "fixtures" / "site"
CONTENT_TYPES = {
    ".xml": "application/xml; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class SiteServer:
    def __init__(self):
        self.requests: list[str] = []
        self.changing_body = "<html lang='en'><body><p>Version one of a changing synthetic page.</p></body></html>"
        self.headers_for: dict[str, dict[str, str]] = {}
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_GET(self):  # noqa: N802
                server.requests.append(self.path)
                path = self.path.split("?", 1)[0]
                host = self.headers.get("Host", "")
                if path.startswith("/down/"):
                    return self._send(503, "text/plain", b"down")
                if path == "/forbidden.html":
                    return self._send(403, "text/html", b"<p>forbidden</p>")
                if path == "/unauthorized.html":
                    return self._send(401, "text/html", b"<p>login required</p>")
                if path == "/paywall.html":
                    return self._send(402, "text/html", b"<p>subscribe</p>")
                if path == "/big.html":
                    return self._send(200, "text/html", b"<p>" + b"x" * 300_000 + b"</p>")
                if path == "/binary.bin":
                    return self._send(200, "application/octet-stream", b"\x00\x01")
                if path == "/redirect.html":
                    self.send_response(302)
                    self.send_header("Location", "/news/logistics-training-en.html")
                    self.end_headers()
                    return
                if path == "/changing.html":
                    return self._send(200, "text/html; charset=utf-8", server.changing_body.encode("utf-8"))
                file = (SITE_DIR / path.lstrip("/")).resolve()
                if SITE_DIR not in file.parents or not file.is_file():
                    return self._send(404, "text/plain", b"not found")
                body = file.read_bytes()
                if file.suffix in (".xml", ".html", ".json"):
                    body = body.replace(b"HOST", host.encode())
                self._send(200, CONTENT_TYPES.get(file.suffix, "application/octet-stream"), body,
                           server.headers_for.get(path, {}))

            def _send(self, code, ctype, body, extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
