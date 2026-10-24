"""Minimal fake upstream MCP server for the Step 1 standalone proof.

Threading HTTP server speaking JSON-RPC 2.0. tools/call behavior:
  - "get_customer" -> result text carries the well-known dummy SSN
    123-45-6789 (matches no real person; same dummy the package's own
    dashboard demo uses) to trigger local PII result screening.
  - anything else  -> clean result echoing the tool name.
Counts tools/call requests in /tmp so the proof can show that a
blocked call never reached the upstream. (Proof-only helper; not
part of the shipped unit.)
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COUNT_FILE = sys.argv[2] if len(sys.argv) > 2 else "/tmp/rs_proof_upstream_count"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        method = body.get("method")
        req_id = body.get("id")
        if method == "tools/call":
            try:
                with open(COUNT_FILE, "a") as f:
                    f.write("tools/call\n")
            except OSError:
                pass
            name = (body.get("params") or {}).get("name", "")
            if name == "get_customer":
                text = ("Customer record: Jane Doe, SSN 123-45-6789, "
                        "account in good standing.")
            else:
                text = f"clean result from {name}"
            result = {"content": [{"type": "text", "text": text}]}
            payload = {"jsonrpc": "2.0", "id": req_id, "result": result}
        elif method == "initialize":
            payload = {"jsonrpc": "2.0", "id": req_id,
                       "result": {"protocolVersion": "2025-03-26",
                                  "capabilities": {},
                                  "serverInfo": {"name": "fake-upstream",
                                                 "version": "0.0.0"}}}
        elif method == "tools/list":
            payload = {"jsonrpc": "2.0", "id": req_id,
                       "result": {"tools": []}}
        else:
            payload = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19001
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
