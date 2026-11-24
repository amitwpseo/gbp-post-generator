"""Exercises the real google-genai SDK against a local stand-in server (no key or network needed)."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import config
import gemini_client
from gemini_client import GeminiError, Turn


def make_server(behavior, listed):
    """behavior: {model: ('ok', text) | ('404',) | ('429', message)}; listed: model names for GET /models."""
    log = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, payload):
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if "/models" in self.path:
                self._send(200, {"models": [
                    {"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]} for n in listed
                ] + [{"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]}]})
            else:
                self._send(404, {"error": {"code": 404, "message": "nope", "status": "NOT_FOUND"}})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            model = self.path.split("/models/")[1].split(":")[0]
            log.append(model)
            kind = behavior.get(model, ("404",))
            if kind[0] == "ok":
                self._send(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": kind[1]}]},
                                                 "finishReason": "STOP"}]})
            elif kind[0] == "429":
                self._send(429, {"error": {"code": 429, "message": kind[1], "status": "RESOURCE_EXHAUSTED"}})
            else:
                self._send(404, {"error": {"code": 404, "message": f"models/{model} is not found",
                                           "status": "NOT_FOUND"}})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, log


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        gemini_client._working_model = None
        self.sleeps = []
        self.sleep_patch = mock.patch.object(gemini_client, "_sleep", lambda s: self.sleeps.append(s))
        self.sleep_patch.start()
        self.servers = []

    def tearDown(self):
        self.sleep_patch.stop()
        gemini_client._working_model = None
        for s in self.servers:
            s.shutdown()

    def env(self, server, **extra):
        values = {"GOOGLE_GEMINI_BASE_URL": f"http://127.0.0.1:{server.server_port}", "GEMINI_API_KEY": "test",
                  "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1",
                  "GEMINI_MODEL": "gemini-old-flash", "GEMINI_FALLBACK_MODELS": "gemini-old-flash-lite"}
        values.update(extra)
        return mock.patch.dict(os.environ, values)

    def start(self, behavior, listed):
        server, log = make_server(behavior, listed)
        self.servers.append(server)
        return server, log

    def test_configured_models_retired_discovers_a_working_one(self):
        server, log = self.start({"gemini-new-flash": ("ok", "hello")},
                                 ["gemini-new-flash", "gemini-new-flash-image", "gemini-new-flash-preview-tts"])
        with self.env(server):
            self.assertEqual(gemini_client.generate([Turn("user", "hi")]), "hello")
            self.assertEqual(log, ["gemini-old-flash", "gemini-old-flash-lite", "gemini-new-flash"])
            self.assertEqual(gemini_client.working_model(), "gemini-new-flash")
            log.clear()
            gemini_client.generate([Turn("user", "again")])
            self.assertEqual(log, ["gemini-new-flash"])  # remembered, no more dead-model round trips

    def test_nothing_usable_gives_actionable_error(self):
        server, _ = self.start({}, ["gemini-new-flash", "gemini-newer-flash"])
        with self.env(server):
            with self.assertRaises(GeminiError) as ctx:
                gemini_client.generate([Turn("user", "hi")])
        msg = str(ctx.exception)
        self.assertIn("gemini-old-flash (not found)", msg)
        self.assertIn("gemini-new-flash", msg)
        self.assertIn("GEMINI_MODEL", msg)

    def test_zero_quota_model_is_skipped_without_waiting(self):
        server, log = self.start(
            {"gemini-old-flash": ("429", "Quota exceeded for metric x, limit: 0, model: gemini-old-flash"),
             "gemini-old-flash-lite": ("ok", "lite works")}, [])
        with self.env(server):
            self.assertEqual(gemini_client.generate([Turn("user", "hi")]), "lite works")
        self.assertEqual(self.sleeps, [])
        self.assertEqual(log, ["gemini-old-flash", "gemini-old-flash-lite"])

    def test_plain_rate_limit_retries_then_reports_quota(self):
        server, _ = self.start({"gemini-old-flash": ("429", "Too many requests"),
                                "gemini-old-flash-lite": ("429", "Too many requests")}, [])
        with self.env(server):
            with self.assertRaises(GeminiError) as ctx:
                gemini_client.generate([Turn("user", "hi")])
        self.assertEqual(ctx.exception.status, 429)
        self.assertIn("quota", str(ctx.exception))
        self.assertTrue(self.sleeps)

    def test_ranking_prefers_stable_full_flash_newest(self):
        names = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.8-flash"]
        self.assertEqual(sorted(names, key=gemini_client._model_rank),
                         ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview"])

    def test_default_models_are_not_the_retired_ones(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for var in ("GEMINI_MODEL", "GEMINI_FALLBACK_MODELS"):
                os.environ.pop(var, None)
            self.assertFalse(any("2.5" in m for m in config.models()))


if __name__ == "__main__":
    unittest.main()
