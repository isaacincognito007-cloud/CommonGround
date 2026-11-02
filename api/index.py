"""Vercel WSGI adapter for CommonGround.

Owner: Isaac Shiloah Herbert V · ISAAC.INCOGNITO007
"""
from __future__ import annotations

import io
import logging
import os
import sys
import threading
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Vercel terminates HTTPS before invoking the function. Preserve an explicit
# operator setting, but default secure cookies on the hosted runtime.
if os.environ.get("VERCEL") == "1":
    os.environ.setdefault("CG_SECURE_COOKIE", "1")

import server  # noqa: E402

_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def _ensure_database() -> None:
    """Initialize schema once per function instance; never use ephemeral SQLite on Vercel."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:
            return
        if os.environ.get("VERCEL") == "1" and not server.get_database_url():
            raise RuntimeError("Set DATABASE_URL or POSTGRES_URL for persistent Vercel storage.")
        server.init_db(seed=False)
        _INITIALIZED = True


def _request_path(environ: dict) -> tuple[str, str]:
    """Recover the browser path carried through the single-function rewrite."""
    path = str(environ.get("PATH_INFO") or "/")
    pairs = parse_qsl(str(environ.get("QUERY_STRING") or ""), keep_blank_values=True)
    forwarded = next((value for key, value in pairs if key == "__cg_path"), None)
    if forwarded and path.rstrip("/") in {"/api", "/api/index", "/api/index.py"}:
        path = forwarded
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or "\x00" in path
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        path = "/"
    query = urlencode([(key, value) for key, value in pairs if key != "__cg_path"])
    return path, query


def _headers(environ: dict) -> Message:
    message = Message()
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            name = key[5:].replace("_", "-")
            message.add_header(name, str(value))
    if environ.get("CONTENT_TYPE"):
        message["Content-Type"] = str(environ["CONTENT_TYPE"])
    if environ.get("CONTENT_LENGTH") is not None:
        message["Content-Length"] = str(environ["CONTENT_LENGTH"])
    return message


class _FunctionRequestHandler(server.Handler):
    """Run the existing HTTP handler against in-memory WSGI streams."""

    def __init__(self, environ: dict, body: bytes, path: str, query: str):
        self.command = str(environ.get("REQUEST_METHOD") or "GET").upper()
        self.path = path + ("?" + query if query else "")
        self.requestline = f"{self.command} {self.path} HTTP/1.1"
        self.request_version = "HTTP/1.1"
        self.headers = _headers(environ)
        client_ip = str(environ.get("REMOTE_ADDR") or "127.0.0.1")
        self.client_address = (client_ip, 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self._status = 500
        self._response_headers: list[tuple[str, str]] = []

    def send_response(self, code, message=None):
        self._status = int(code)

    def send_header(self, keyword, value):
        self._response_headers.append((str(keyword), str(value)))

    def end_headers(self):
        return None

    def log_message(self, fmt, *args):
        logging.info("CommonGround request: %s %s", self.command, urlsplit(self.path).path)


def _response_headers(handler: _FunctionRequestHandler) -> list[tuple[str, str]]:
    headers = list(handler._response_headers)
    present = {name.lower() for name, _ in headers}
    defaults = (
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "same-origin"),
        ("X-Frame-Options", "DENY"),
        ("Cache-Control", "no-store"),
    )
    headers.extend((name, value) for name, value in defaults if name.lower() not in present)
    return headers


def application(environ, start_response):
    """WSGI entry point supported by Vercel's Python runtime."""
    try:
        _ensure_database()
    except Exception as exc:
        logging.error("CommonGround database initialization failed (%s)", type(exc).__name__)
        payload = b'{"error":{"code":"storage_unavailable","field":"request","message":"Persistent storage is not configured or is temporarily unavailable."}}'
        start_response(
            "503 Service Unavailable",
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload))),
             ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")],
        )
        return [payload]

    method = str(environ.get("REQUEST_METHOD") or "GET").upper()
    if method not in {"GET", "HEAD", "POST"}:
        payload = b'{"error":{"code":"method_not_allowed","field":"request","message":"Use GET or POST."}}'
        start_response(
            "405 Method Not Allowed",
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload))),
             ("Allow", "GET, HEAD, POST"), ("Cache-Control", "no-store")],
        )
        return [b"" if method == "HEAD" else payload]

    try:
        path, query = _request_path(environ)
        raw_length = str(environ.get("CONTENT_LENGTH") or "0")
        try:
            length = int(raw_length)
        except ValueError:
            length = 0
        max_body = int(getattr(server, "MAX_BODY", 65536))
        stream = environ.get("wsgi.input") or io.BytesIO()
        body = stream.read(length) if 0 <= length <= max_body else b""
        handler = _FunctionRequestHandler(environ, body, path, query)
        if method in {"GET", "HEAD"}:
            handler.do_GET()
        else:
            handler.do_POST()
        payload = handler.wfile.getvalue()
        headers = _response_headers(handler)
        try:
            phrase = HTTPStatus(handler._status).phrase
        except ValueError:
            phrase = "Unknown"
        start_response(f"{handler._status} {phrase}", headers)
        return [b"" if method == "HEAD" else payload]
    except Exception as exc:
        logging.error("CommonGround WSGI request failed (%s)", type(exc).__name__)
        payload = b'{"error":{"code":"server_error","field":"request","message":"Could not complete this request. Please retry."}}'
        start_response(
            "500 Internal Server Error",
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload))),
             ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")],
        )
        return [payload]


# Vercel accepts either a top-level `app` or `application` WSGI object.
app = application
