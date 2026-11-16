#!/usr/bin/env python3
"""Mock Worker for collector local test, test only, never deploy.

Listens on 127.0.0.1:8092, accepts POST /api/gate-verdicts, checks
header X-RS-Collector-Secret against env MOCK_WORKER_SECRET, appends
each received batch as one JSON line to /tmp/mock-worker.log, and
returns 200 with {"ok": true, "stored": <count>}.
If the secret header is missing or mismatched, returns 401 and stores
nothing, mirroring the production Worker endpoint design.

Usage, Test window only:
  read -s "MOCK_WORKER_SECRET?Test collector secret: "
  export MOCK_WORKER_SECRET
  python3 mock_worker_for_collector.py
  # In another window, run the collector with the same secret as
  # MCP_PROXY_COLLECTOR_SECRET, against
  # http://127.0.0.1:8092/api/gate-verdicts
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SECRET = os.environ.get("MOCK_WORKER_SECRET", "").strip()
LOG = Path("/tmp/mock-worker.log")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != "/api/gate-verdicts":
            self.send_response(404)
            self.end_headers()
            return
        if not SECRET or self.headers.get("X-RS-Collector-Secret") != SECRET:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"ok": false, "error": "unauthorized"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body or b"{}")
            count = len(data.get("verdicts", []))
        except Exception:
            count = 0
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(body.decode("utf-8", errors="replace") + "\n")
        payload = json.dumps({"ok": True, "stored": count}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    if not SECRET:
        print("ABORT: MOCK_WORKER_SECRET is required.")
        raise SystemExit(1)
    print("Mock Worker listening on :8092, log /tmp/mock-worker.log")
    HTTPServer(("127.0.0.1", 8092), Handler).serve_forever()
