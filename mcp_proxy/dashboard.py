"""Visual dashboard for the MCP Proxy Firewall.

Two modes:

1. Served by the proxy itself:
   GET /_rs/dashboard renders the live dashboard HTML, which polls
   /_rs/neighbors and /_rs/health every 2 seconds.

2. Standalone demo mode (no proxy required):
   python3 -m mcp_proxy.dashboard --demo
   Runs a simulated dashboard with scripted attack scenarios so
   partners can see the visual flow without a live proxy.

The HTML is a single self-contained file (inline CSS/JS, no external
dependencies).
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
_HTML_PATH = os.path.join(_HERE, "dashboard.html")

DEMO_MODE = "--demo" in sys.argv[1:]
DEMO_PORT = int(os.environ.get("MCP_PROXY_DASHBOARD_PORT", "8091"))


def load_html():
    with open(_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Demo data: scripted scenarios mirroring mcp_proxy.demo.
# ---------------------------------------------------------------------------

def _demo_state():
    now = time.strftime("%H:%M:%S")
    return {
        "neighbors": {
            "http://127.0.0.1:9001": {
                "reputation": "clean",
                "flags": [],
            },
            "http://127.0.0.1:9002": {
                "reputation": "quarantined",
                "flags": [
                    {"reason": "prompt_injection: hidden instructions in tool result",
                     "at": now, "poison_category": "prompt_injection"},
                    {"reason": "kit_match: scam-kit fingerprint kit_deadbeef... in tool result",
                     "at": now, "poison_category": "kit_match"},
                    {"reason": "pii_leak: unredacted SSN pattern in tool result (1 occurrence)",
                     "at": now, "poison_category": "pii_leak"},
                    {"reason": "oauth_tampering: OAuth path mimics google on foreign domain",
                     "at": now, "poison_category": "oauth_tampering"},
                    {"reason": "credential_exfiltration: JWT in tool result bound for non-IdP domain(s)",
                     "at": now, "poison_category": "credential_exfiltration"},
                ],
            },
        },
        "quarantine_events": [
            {"url": "http://127.0.0.1:9002",
             "reason": "auto-quarantined after 3 flags: poisoned neighbor",
             "at": now},
        ],
        "verdict_pubkey": "demo-pubkey-" + "ab" * 16,
        "verdicts_signed": True,
    }


class _DemoHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, ctype="application/json", code=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/_rs/dashboard"):
            self._send(load_html(), "text/html; charset=utf-8")
        elif path == "/_rs/neighbors":
            self._send(json.dumps(_demo_state()))
        elif path == "/_rs/health":
            self._send(json.dumps({"status": "ok",
                                   "version": "RelayShield-MCP-Proxy/demo",
                                   "verdicts_signed": True}))
        else:
            self._send(json.dumps({"error": "not found"}), code=404)


def run_demo_server(port=DEMO_PORT):
    srv = http.server.HTTPServer(("127.0.0.1", port), _DemoHandler)
    print(f"RelayShield MCP Proxy dashboard (demo mode)")
    print(f"Open http://127.0.0.1:{port}/_rs/dashboard in your browser.")
    print("Press Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    if DEMO_MODE:
        run_demo_server()
    else:
        print("dashboard.py is served by the proxy at GET /_rs/dashboard.")
        print("For standalone demo mode: python3 -m mcp_proxy.dashboard --demo")


if __name__ == "__main__":
    main()
