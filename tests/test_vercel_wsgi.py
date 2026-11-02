"""Local WSGI regression tests. Owner: Isaac Shiloah Herbert V · ISAAC.INCOGNITO007."""
from __future__ import annotations

import importlib
import io
import json
import os
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VercelWSGITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_env = {key: os.environ.get(key) for key in ("CG_DB", "DATABASE_URL", "POSTGRES_URL", "VERCEL", "CG_SECURE_COOKIE", "CG_ORIGIN")}
        for key in ("DATABASE_URL", "POSTGRES_URL", "VERCEL"):
            os.environ.pop(key, None)
        cls._tempdir = tempfile.TemporaryDirectory(prefix="commonground-wsgi-")
        os.environ["CG_DB"] = str(Path(cls._tempdir.name) / "test.sqlite3")
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.server = importlib.import_module("server")
        cls._saved_server_state = {name: getattr(cls.server, name) for name in ("DB", "PUBLIC_ORIGIN", "SECURE")}
        cls.server.DB = os.environ["CG_DB"]
        cls.server.PUBLIC_ORIGIN = ""
        cls.server.SECURE = False
        cls.api = importlib.import_module("api.index")
        cls._saved_api_initialized = cls.api._INITIALIZED
        cls.api._INITIALIZED = False
        cls.api._ensure_database()
        with cls.server.connect() as conn:
            conn.execute(
                "INSERT INTO users(id,name,email,password,role,group_name,verified,credentials) VALUES(?,?,?,?,?,?,?,?)",
                ("wsgi-member", "WSGI Member", "wsgi.member@example.test", cls.server.password_hash("test-only-password"), "member", "Workshop", 1, '["Workshop induction"]'),
            )
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for name, value in cls._saved_server_state.items():
            setattr(cls.server, name, value)
        cls.api._INITIALIZED = cls._saved_api_initialized
        cls._tempdir.cleanup()

    def request(self, path, method="GET", payload=None, headers=None, query=""):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/json" if method == "POST" else "",
            "CONTENT_LENGTH": str(len(body)),
            "SERVER_NAME": "example.test",
            "SERVER_PORT": "80",
            "HTTP_HOST": "example.test",
            "REMOTE_ADDR": "127.0.0.10",
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(body),
        }
        for key, value in (headers or {}).items():
            env["HTTP_" + key.upper().replace("-", "_")] = value
        captured = {}
        def start_response(status, response_headers, exc_info=None):
            captured["status"] = int(status.split()[0])
            captured["headers"] = response_headers
        content = b"".join(self.api.application(env, start_response))
        return captured["status"], dict(captured["headers"]), content

    def test_root_static_assets_and_api_health_through_rewrite(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"CommonGround", body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        for path, mime in (("/app.js", "javascript"), ("/style.css", "text/css"), ("/favicon.svg", "image/svg+xml")):
            with self.subTest(path=path):
                code, response_headers, payload = self.request(path)
                self.assertEqual(code, 200)
                self.assertIn(mime, response_headers.get("Content-Type", ""))
                self.assertTrue(payload)
        code, response_headers, payload = self.request("/api", query="__cg_path=%2Fapi%2Fhealth")
        self.assertEqual(code, 200, payload)
        self.assertEqual(json.loads(payload)["timezone"], "Asia/Kolkata")

    def test_login_cookie_and_session_restore(self):
        status, headers, body = self.request(
            "/api", method="POST", payload={"email": "wsgi.member@example.test", "password": "test-only-password"},
            headers={"Origin": "http://example.test"}, query="__cg_path=%2Fapi%2Flogin",
        )
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertEqual(data["user"]["id"], "wsgi-member")
        cookie = SimpleCookie(); cookie.load(headers["Set-Cookie"])
        token = cookie["cg_session"].value
        self.assertTrue(token)
        status, _, body = self.request("/api", headers={"Cookie": f"cg_session={token}"}, query="__cg_path=%2Fapi%2Fsession")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["user"]["email"], "wsgi.member@example.test")


if __name__ == "__main__":
    unittest.main()
