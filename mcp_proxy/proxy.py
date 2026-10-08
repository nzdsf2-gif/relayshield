"""Transparent MCP proxy firewall.

Speaks JSON-RPC 2.0 over HTTP. MCP clients (agents) connect to this
proxy as if it were the MCP server. The proxy forwards requests to
the configured upstream server, screening tools/call invocations
against RelayShield threat intelligence first.

Supported methods: initialize, tools/list, tools/call.
Notifications (no id) are forwarded fire-and-forget.
"""

import json
import logging
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import ProxyConfig
from .screener import Screener

log = logging.getLogger(__name__)

# MCP error codes (JSON-RPC 2.0 compatible).
ERR_BLOCKED_BY_POLICY = -32001


def _forward_jsonrpc(upstream_url: str, payload: dict, timeout: float = 30.0) -> dict:
    """Forward a JSON-RPC payload to the upstream server."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        upstream_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _error_response(req_id, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP JSON-RPC traffic."""

    server_version = "RelayShield-MCP-Proxy/0.1.0"

    def log_message(self, fmt, *args):
        # Route through logging instead of stderr.
        log.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        cfg: ProxyConfig = self.server.cfg
        screener: Screener = self.server.screener

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(
                _error_response(None, -32700, "Parse error: invalid JSON"), 400
            )
            return

        # Support batch requests minimally: process each in order.
        is_batch = isinstance(payload, list)
        requests = payload if is_batch else [payload]
        responses = []

        for req in requests:
            resp = self._handle_one(req, cfg, screener)
            if resp is not None:  # None = notification, no response
                responses.append(resp)

        if is_batch:
            self._send_json(responses)
        elif responses:
            self._send_json(responses[0])
        else:
            # Notification only: 202 accepted, no body per JSON-RPC.
            self.send_response(202)
            self.end_headers()

    def _handle_one(self, req: dict, cfg: ProxyConfig, screener: Screener):
        req_id = req.get("id")
        method = req.get("method", "")
        is_notification = "id" not in req

        # Notifications: forward fire-and-forget, no response.
        if is_notification:
            try:
                _forward_jsonrpc(cfg.upstream_url, req)
            except Exception as exc:
                log.warning("notification forward failed: %s", exc)
            return None

        if method == "tools/call":
            return self._handle_tools_call(req, req_id, cfg, screener)

        # initialize, tools/list, and anything else: pure passthrough.
        start = time.monotonic()
        try:
            upstream_resp = _forward_jsonrpc(cfg.upstream_url, req)
        except Exception as exc:
            log.error("upstream forward failed for %s: %s", method, exc)
            return _error_response(req_id, -32603, "Upstream MCP server error",
                                   {"detail": str(exc)})
        elapsed_ms = (time.monotonic() - start) * 1000
        log.info(json.dumps({
            "event": "proxied",
            "method": method,
            "id": req_id,
            "upstream_ms": round(elapsed_ms, 1),
        }))
        # Ensure the response carries our request id.
        if isinstance(upstream_resp, dict) and "id" not in upstream_resp:
            upstream_resp["id"] = req_id
        return upstream_resp

    def _handle_tools_call(self, req: dict, req_id, cfg: ProxyConfig,
                           screener: Screener):
        params = req.get("params") or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        t0 = time.monotonic()

        verdict = {"verdict": "allow", "level": "unknown",
                   "reasons": ["screening disabled"]}
        screen_ms = 0.0
        if cfg.screening_enabled:
            try:
                s0 = time.monotonic()
                verdict = screener.screen_tool_call(tool_name, arguments)
                screen_ms = (time.monotonic() - s0) * 1000
            except Exception as exc:
                log.error("screener error: %s", exc)
                verdict = {"verdict": "allow", "level": "unknown",
                           "reasons": [f"screener error, allowed: {exc}"]}

        total_ms = (time.monotonic() - t0) * 1000
        log.info(json.dumps({
            "event": "tools_call",
            "tool": tool_name,
            "verdict": verdict.get("verdict"),
            "level": verdict.get("level"),
            "score": verdict.get("score", 0),
            "reasons": verdict.get("reasons", []),
            "screen_ms": round(screen_ms, 1),
            "total_ms": round(total_ms, 1),
            "screening_enabled": cfg.screening_enabled,
        }))

        if verdict.get("verdict") == "block":
            return _error_response(
                req_id,
                ERR_BLOCKED_BY_POLICY,
                f"Blocked by RelayShield: tool '{tool_name}' arguments "
                f"flagged at level '{verdict.get('level')}'.",
                {
                    "tool": tool_name,
                    "level": verdict.get("level"),
                    "score": verdict.get("score", 0),
                    "reasons": verdict.get("reasons", []),
                },
            )

        # Clean: forward to upstream.
        try:
            upstream_resp = _forward_jsonrpc(cfg.upstream_url, req)
        except Exception as exc:
            log.error("upstream tools/call failed: %s", exc)
            return _error_response(req_id, -32603, "Upstream MCP server error",
                                   {"detail": str(exc)})
        if isinstance(upstream_resp, dict) and "id" not in upstream_resp:
            upstream_resp["id"] = req_id
        return upstream_resp


class ProxyServer(HTTPServer):
    """HTTPServer carrying proxy config and screener."""

    def __init__(self, cfg: ProxyConfig):
        self.cfg = cfg
        self.screener = Screener(
            api_base=cfg.rs_api_base,
            api_key=cfg.rs_api_key,
            timeout=cfg.screen_timeout,
            block_levels=cfg.block_level_set,
        )
        super().__init__(("0.0.0.0", cfg.listen_port), ProxyHandler)


def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = ProxyConfig()
    problems = cfg.validate()
    if problems:
        for p in problems:
            log.error("config: %s", p)
        raise SystemExit(1)
    server = ProxyServer(cfg)
    log.info("MCP proxy listening on :%d, upstream=%s, screening=%s",
             cfg.listen_port, cfg.upstream_url, cfg.screening_enabled)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
