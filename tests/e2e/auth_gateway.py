"""LOCAL TEST-ONLY Supabase-compatible gateway for the browser E2E (never used against a real project).

The web app talks to Supabase through two HTTP APIs: GoTrue (``/auth/v1``) and PostgREST (``/rest/v1``). In the
throw-away E2E stack this single process provides both on one port:

* ``/auth/v1`` — the minimal GoTrue subset that ``@supabase/supabase-js`` / ``@supabase/ssr`` use for e-mail +
  password sign-in: ``POST /token?grant_type=password|refresh_token``, ``GET /user``, ``POST /logout``. Users and their
  passwords are supplied by the E2E fixture at start-up (random, per run; nothing is stored or committed).
* ``/rest/v1`` — a transparent reverse proxy to a real PostgREST process.

Tokens are HS256 JWTs signed with a per-run random secret shared with PostgREST, carrying ``role=authenticated`` and
``sub=<user id>`` exactly like Supabase, so ``auth.uid()`` and every HUMAN_ONLY check run unchanged in PostgreSQL.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_jwt(claims: dict, secret: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(sig)}"


def verify_jwt(token: str, secret: str) -> dict | None:
    try:
        header, body, sig = token.split(".")
        expected = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        claims = json.loads(_unb64(body))
        if claims.get("exp", 0) < time.time():
            return None
        return claims
    except (ValueError, json.JSONDecodeError):
        return None


@dataclass
class GatewayUser:
    id: str
    email: str
    password: str


@dataclass
class Gateway:
    postgrest_port: int
    jwt_secret: str
    users: dict[str, GatewayUser] = field(default_factory=dict)
    refresh: dict[str, str] = field(default_factory=dict)          # refresh token -> user id
    port: int = 0
    _server: ThreadingHTTPServer | None = None

    def anon_key(self) -> str:
        return sign_jwt({"role": "anon", "iss": "lfhe-e2e", "exp": int(time.time()) + 86400 * 30}, self.jwt_secret)

    def add_user(self, user_id: str, email: str, password: str) -> None:
        self.users[email.lower()] = GatewayUser(user_id, email.lower(), password)

    def user_json(self, u: GatewayUser) -> dict:
        return {"id": u.id, "aud": "authenticated", "role": "authenticated", "email": u.email,
                "email_confirmed_at": "2026-01-01T00:00:00Z", "phone": "", "app_metadata": {"provider": "email"},
                "user_metadata": {}, "identities": [], "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z"}

    def session(self, u: GatewayUser) -> dict:
        now = int(time.time())
        access = sign_jwt({"sub": u.id, "role": "authenticated", "aud": "authenticated", "email": u.email,
                           "iat": now, "exp": now + 3600, "session_id": secrets.token_hex(8)}, self.jwt_secret)
        rt = secrets.token_urlsafe(24)
        self.refresh[rt] = u.id
        return {"access_token": access, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600,
                "refresh_token": rt, "user": self.user_json(u)}

    def start(self) -> int:
        gw = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):          # quiet
                return

            def _send(self, status: int, payload: dict | None = None, headers: dict | None = None):
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _body(self) -> bytes:
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _auth(self, method: str):
                url = urllib.parse.urlparse(self.path)
                path = url.path[len("/auth/v1"):]
                q = urllib.parse.parse_qs(url.query)
                raw = self._body()
                data = json.loads(raw) if raw else {}
                if method == "POST" and path == "/token":
                    grant = (q.get("grant_type") or [""])[0]
                    if grant == "password":
                        u = gw.users.get(str(data.get("email", "")).lower())
                        if u is None or not hmac.compare_digest(u.password, str(data.get("password", ""))):
                            return self._send(400, {"error": "invalid_grant", "error_description": "Invalid login credentials",
                                                    "code": "invalid_credentials", "msg": "Invalid login credentials"})
                        return self._send(200, gw.session(u))
                    if grant == "refresh_token":
                        uid = gw.refresh.pop(str(data.get("refresh_token", "")), None)
                        u = next((x for x in gw.users.values() if x.id == uid), None)
                        if u is None:
                            return self._send(400, {"error": "invalid_grant", "code": "refresh_token_not_found",
                                                    "msg": "Invalid Refresh Token"})
                        return self._send(200, gw.session(u))
                    return self._send(400, {"error": "unsupported_grant_type", "msg": "unsupported grant"})
                if method == "GET" and path == "/user":
                    token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
                    claims = verify_jwt(token, gw.jwt_secret)
                    u = next((x for x in gw.users.values() if claims and x.id == claims.get("sub")), None)
                    if u is None:
                        return self._send(401, {"code": "bad_jwt", "msg": "invalid JWT"})
                    return self._send(200, gw.user_json(u))
                if method == "POST" and path == "/logout":
                    return self._send(204)
                return self._send(404, {"msg": f"not implemented in the E2E gateway: {method} {path}"})

            def _proxy(self, method: str):
                body = self._body()
                path = self.path[len("/rest/v1"):] or "/"
                headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length",
                                                                                      "connection", "apikey")}
                conn = http.client.HTTPConnection("127.0.0.1", gw.postgrest_port, timeout=120)
                try:
                    conn.request(method, path, body=body or None, headers=headers)
                    resp = conn.getresponse()
                    data = resp.read()
                finally:
                    conn.close()
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def _route(self, method: str):
                if self.path.startswith("/auth/v1"):
                    return self._auth(method)
                if self.path.startswith("/rest/v1"):
                    return self._proxy(method)
                return self._send(404, {"msg": "unknown path"})

            def do_GET(self):  # noqa: N802
                self._route("GET")

            def do_POST(self):  # noqa: N802
                self._route("POST")

            def do_PATCH(self):  # noqa: N802
                self._route("PATCH")

            def do_DELETE(self):  # noqa: N802
                self._route("DELETE")

            def do_HEAD(self):  # noqa: N802
                self._route("HEAD")

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
